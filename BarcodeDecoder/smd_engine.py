#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smd_engine.py — Единое ядро парсинга компонентов SMD, тем оформления и общих UI-утилит.
Используется во всех приложениях экосистемы: SMD Hub, BarcodeDecoder, Unification, PnP_Manager.

Содержит:
- Эталонный движок распознавания 16 производителей SMD конденсаторов и резисторов
- Очистку префиксов катушек и токенизацию составных 2D кодов (ISO 15434 / DataMatrix / QR)
- Поддержку 0-омных джамперов с погрешностью (например, R_0402_0R_1%)
- Парсинг российских резисторов Р1-12 / Р1-16
- Цветовую дизайн-систему THEMES (Dark & Light)
- Всплывающие подсказки ToolTip, диалоги FAQ и Обратной связи
"""

import os
import sys
import re
import json
import subprocess
import ctypes
import webbrowser
import urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Union, Optional, Tuple

try:
    import winreg
except ImportError:
    winreg = None


# =============================================================================
# Форматирование и базовые утилиты парсинга
# =============================================================================
MAX_TRIM_LEFT = 15
MAX_TRIM_RIGHT = 80


def format_g(num: float) -> str:
    """
    Форматирует число в компактную строку без научной нотации,
    с удалением незначащих нулей — аналог Kotlin DecimalFormat("0.######").
    """
    if num == 0:
        return '0'
    result = f"{num:.6f}"
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return result


def parse_russian_resistor_value(raw: str) -> str:
    """
    Преобразует российское и международное обозначение резистора (ГОСТ 28883-90 / IEC 60062)
    в канонический формат с суффиксами R/K/M.
    
    Поддерживаемые форматы:
    - Буква как разделитель целой и дробной части (ГОСТ/IEC):
      '4к7', '4k7' -> '4.7K'
      '4R7', '4r7' -> '4.7R'
      '1м5', '1m5', '1M5' -> '1.5M'
      '0R22', 'R22' -> '0.22R'
      'к47', 'k47' -> '0.47K'
    - Суффиксная форма:
      '100Ом', '100 ом', '100R' -> '100R'
      '4.7кОм', '4,7ком', '4.7k' -> '4.7K'
      '1МОм', '1M' -> '1M'
    - Числа без букв:
      '100' -> '100R'
      '1500' -> '1.5K'
      '0', '0R' -> '0R'
    """
    original = raw.strip()
    if not original:
        return ""
    
    s = original.lower().replace(' ', '')
    s = s.replace('ом', '').replace('ohm', '').replace('ω', '')
    
    # Обработка перемычек / нулей
    if s in ('0', '0r', '00', '000', '0000'):
        return '0R'
    
    # 1. Формат ГОСТ/IEC с буквой-множителем на месте десятичной точки:
    # Примеры: '4к7', '4k7', '4r7', '1м5', '1m5', '0r22', 'r22', 'к47', 'k47', 'м10'
    m_mid = re.match(r'^(\d*)([rkmкkмm])(\d+)$', s)
    if m_mid:
        int_part = m_mid.group(1) or '0'
        unit_char = m_mid.group(2)
        dec_part = m_mid.group(3)
        try:
            val = float(f"{int_part}.{dec_part}")
            if unit_char in ('к', 'k'):
                return f"{format_g(val)}K"
            elif unit_char in ('м', 'm'):
                return f"{format_g(val)}M"
            else:
                return f"{format_g(val)}R"
        except (ValueError, TypeError):
            return original

    # 2. Формат с суффиксом в конце: '4.7к', '4,7k', '100r', '10k', '1m', '100'
    m_end = re.match(r'^([\d.,]+)\s*([rkmкkмm]?)$', s)
    if m_end:
        num_str = m_end.group(1).replace(',', '.')
        unit_char = m_end.group(2)
        try:
            val = float(num_str)
        except (ValueError, TypeError):
            return original

        if unit_char in ('к', 'k'):
            return f"{format_g(val)}K"
        elif unit_char in ('м', 'm'):
            return f"{format_g(val)}M"
        elif unit_char in ('r',):
            return f"{format_g(val)}R"
        else:
            # Масштабирование чистых чисел
            if val >= 1000000:
                return f"{format_g(val / 1000000)}M"
            elif val >= 1000:
                return f"{format_g(val / 1000)}K"
            else:
                return f"{format_g(val)}R"

    return original


def map_lookup(d: dict, key: str, default=None):
    """
    Регистронезависимый поиск ключа в словаре сопоставления.
    """
    if not d or key is None:
        return default if default is not None else (key.upper() if isinstance(key, str) else key)
    key_str = str(key).strip()
    if key_str in d:
        return d[key_str]
    if key_str.upper() in d:
        return d[key_str.upper()]
    if key_str.lower() in d:
        return d[key_str.lower()]
    for k, v in d.items():
        if str(k).lower() == key_str.lower():
            return v
    return default if default is not None else key_str.upper()


# =============================================================================
# Регулярное выражение префиксов катушек (EIA/CEA-863, EDIFACT, etc.)
# =============================================================================
BARCODE_PREFIX_REGEX = re.compile(
    r'^(?:ITEM\(1P\)|CUST\s*PROD\s*ID\(P\)|CUST\s*P/N|OUR\s*P/N|TDK\s*ITEM|P/N|ITEM|\(1P\)|\(30P\)|\(31P\)|\(1T\)|\(1S\)|\(6P\)|\(Q\)|\(V\)|\(P\)|1P|30P|31P|P|1T|1S|6P|9D|Q|V|K|D|10D|11D|12D)[:\s\-]*',
    re.IGNORECASE
)


# =============================================================================
# Класс правила производителя
# =============================================================================
class VendorRule:
    def __init__(self, name, comp_type, pattern, size_map, dielectric_map=None, voltage_map=None,
                 tolerance_map=None, value_parser=None, suffix_map=None, is_resistor=False):
        self.name = name
        self.comp_type = comp_type
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.size_map = size_map
        self.dielectric_map = dielectric_map or {}
        self.voltage_map = voltage_map or {}
        self.tolerance_map = tolerance_map or {}
        self.value_parser = value_parser
        self.suffix_map = suffix_map or {}
        self.is_resistor = is_resistor

    def match(self, code: str):
        m = self.pattern.match(code)
        if m:
            return m.groupdict()
        return None


# =============================================================================
# Единый парсер компонентов
# =============================================================================
class VendorParser:
    def __init__(self, rules):
        self.rules = rules

    def parse(self, code: str, vendor_name: str = None):
        original = code.strip()
        if not original:
            return None, None, None, 0, 0

        # 1. Попытка разобрать строку целиком (как единичный токен)
        single_res = self._parse_single_token(original, vendor_name)
        if single_res[0] is not None:
            return single_res

        # 1.1 Попытка с удалением пробелов внутри (для OCR этикеток, например "RC 0402 F R-07 33R2")
        if ' ' in original and not original.upper().startswith(('Р1-', 'P1-')):
            no_spaces = original.replace(' ', '')
            no_space_res = self._parse_single_token(no_spaces, vendor_name)
            if no_space_res[0] is not None:
                return no_space_res

        # 2. Если строка содержит составные разделители (ISO 15434, CSV, &, /, etc.):
        cleaned = original
        if cleaned.startswith("[)>"):
            for sep in ('\u001d', '\u001e', '\n', ',', ';'):
                idx = cleaned.find(sep)
                if 0 < idx < 10:
                    cleaned = cleaned[idx + 1:]
                    break

        tokens = [t.strip() for t in re.split(r'[\u001d\u001e\u0004,;&|\n\r\t/]+', cleaned) if t.strip()]

        for token in tokens:
            token_res = self._parse_single_token(token, vendor_name)
            if token_res[0] is not None:
                return token_res

            if ' ' in token and not token.upper().startswith(('Р1-', 'P1-')):
                token_no_spaces = token.replace(' ', '')
                token_ns_res = self._parse_single_token(token_no_spaces, vendor_name)
                if token_ns_res[0] is not None:
                    return token_ns_res

            m = BARCODE_PREFIX_REGEX.match(token)
            if m:
                stripped = token[m.end():].strip()
                if stripped:
                    stripped_res = self._parse_single_token(stripped, vendor_name)
                    if stripped_res[0] is not None:
                        return stripped_res

                    if ' ' in stripped and not stripped.upper().startswith(('Р1-', 'P1-')):
                        stripped_no_spaces = stripped.replace(' ', '')
                        stripped_ns_res = self._parse_single_token(stripped_no_spaces, vendor_name)
                        if stripped_ns_res[0] is not None:
                            return stripped_ns_res

        return None, None, None, 0, 0

    def _parse_single_token(self, token: str, vendor_name: str = None):
        t = token.strip()
        if not t:
            return None, None, None, 0, 0

        def try_match(candidate: str):
            c = candidate.strip()
            if not c:
                return None, None
            if vendor_name:
                for rule in self.rules:
                    if rule.name.lower() == vendor_name.lower():
                        groups = rule.match(c)
                        if groups:
                            return rule, groups
                return None, None
            else:
                for rule in self.rules:
                    groups = rule.match(c)
                    if groups:
                        return rule, groups
                return None, None

        # 1. Прямое совпадение
        rule, groups = try_match(t)
        if rule is not None:
            return rule, groups, t, 0, 0

        # 2. Если перед кодом стоит стандартный префикс штрихкода (1P, P, etc.)
        m = BARCODE_PREFIX_REGEX.match(t)
        if m:
            stripped = t[m.end():].strip()
            if stripped:
                rule, groups = try_match(stripped)
                if rule is not None:
                    return rule, groups, stripped, m.end(), 0

        # 3. Подбор по обрезке мусорных символов слева и справа
        candidates = []
        max_left = min(MAX_TRIM_LEFT, len(t) - 3) if len(t) > 3 else 0
        max_right = min(MAX_TRIM_RIGHT, len(t) - 3) if len(t) > 3 else 0

        for left in range(0, max_left + 1):
            for right in range(0, max_right + 1):
                if left == 0 and right == 0:
                    continue
                if left + right >= len(t) - 2:
                    continue
                candidates.append((left, right, left + right))

        candidates.sort(key=lambda x: (x[2], x[0]))

        for left, right, _ in candidates:
            candidate = t[left : len(t) - right]
            if not candidate:
                continue
            rule, groups = try_match(candidate)
            if rule is not None:
                return rule, groups, candidate, left, right

        return None, None, None, 0, 0

    def convert_to_unified(self, code: str, rule: VendorRule, groups: dict) -> str:
        """
        Формирует стандартное унифицированное имя компонента:
        R_<Размер>_<Номинал>_<Погрешность> или C_<Размер>_<Диэлектрик>_<Емкость>_<Напряжение>
        """
        if rule.is_resistor:
            size_code = groups.get('size') or groups.get('cga_size') or ''
            size = map_lookup(rule.size_map, size_code, size_code.upper())
            raw_value = groups.get('value') or groups.get('code') or ''
            if raw_value:
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_resistor_value(raw_value, rule.suffix_map)
            else:
                tol_raw = (groups.get('tolerance') or '').upper()
                value_str = '0R' if tol_raw in ('Z', '0') else '?'
            tolerance_code = groups.get('tolerance') or ''
            tolerance = map_lookup(rule.tolerance_map, tolerance_code, tolerance_code.upper())
            
            is_jumper = (value_str == '0R' or tolerance == '0%' or
                         (raw_value.upper() in ('0000', '000', '00', '0', '0R', '0R00', '0R0')) or
                         (raw_value != '' and all(c == '0' for c in raw_value)))
            if is_jumper:
                tol_to_use = tolerance if (tolerance and tolerance.strip()) else '0%'
                return f"R_{size}_0R_{tol_to_use}"
            elif tolerance:
                return f"R_{size}_{value_str}_{tolerance}"
            else:
                return f"R_{size}_{value_str}"
        else:
            size_code = groups.get('size') or groups.get('cga_size') or ''
            size = map_lookup(rule.size_map, size_code, size_code.upper())
            dielectric_code = groups.get('dielectric') or groups.get('temp_code') or ''
            dielectric = map_lookup(rule.dielectric_map, dielectric_code, dielectric_code.upper())
            raw_value = groups.get('code')
            if raw_value:
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_capacitance_value(raw_value)
            else:
                value_str = '?'
            voltage_code = groups.get('voltage') or ''
            voltage = map_lookup(rule.voltage_map, voltage_code, '?')
            return f"C_{size}_{dielectric}_{value_str}_{voltage}"

    def _parse_resistor_value(self, raw: str, suffix_map: dict) -> str:
        raw = raw.strip().upper()
        raw = re.sub(r'Ω', '', raw)
        raw = re.sub(r'(?i)ом', '', raw)

        if raw in ('0000', '000', '00', '0', '0R', '0R00', '0R0'):
            return '0R'

        match_inside = re.match(r'^(\d+)([RKM])(\d*)$', raw)
        if match_inside:
            num_part = match_inside.group(1)
            letter = match_inside.group(2)
            decimal_part = match_inside.group(3)
            val_str = f"{num_part}.{decimal_part}" if decimal_part else num_part
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                val = 0.0
            if letter == 'R':
                return f"{format_g(val)}R"
            elif letter == 'K':
                return f"{format_g(val)}K"
            elif letter == 'M':
                return f"{format_g(val)}M"

        if raw and raw[-1] in suffix_map:
            suffix = raw[-1]
            num_part = raw[:-1]
            unit = suffix_map[suffix]
            if 'R' in num_part:
                num_part = num_part.replace('R', '.')
            try:
                val = float(num_part)
            except (ValueError, TypeError):
                val = 0.0
            if unit in ('Ω', 'mΩ'):
                if unit == 'mΩ':
                    val = val / 1000.0
                if val >= 1000000:
                    return f"{format_g(val / 1000000)}M"
                elif val >= 1000:
                    return f"{format_g(val / 1000)}K"
                else:
                    return f"{format_g(val)}R"
            elif unit == 'KΩ':
                return f"{format_g(val)}K"
            elif unit == 'MΩ':
                return f"{format_g(val)}M"
            else:
                return f"{num_part}{unit}"

        if len(raw) == 3:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except (ValueError, TypeError):
                    val = 0.0
                return f"{format_g(val)}R"
            elif raw.isdigit():
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val >= 1000000:
                    return f"{format_g(val / 1000000)}M"
                elif val >= 1000:
                    return f"{format_g(val / 1000)}K"
                else:
                    return f"{format_g(val)}R"

        if len(raw) == 4:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except (ValueError, TypeError):
                    val = 0.0
                return f"{format_g(val)}R"
            elif raw.isdigit():
                try:
                    mantissa = int(raw[:3])
                    multiplier = int(raw[3])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val >= 1000000:
                    return f"{format_g(val / 1000000)}M"
                elif val >= 1000:
                    return f"{format_g(val / 1000)}K"
                else:
                    return f"{format_g(val)}R"

        return raw

    def _parse_capacitance_value(self, raw: str) -> str:
        raw = raw.strip().upper()
        if 'R' in raw:
            raw = raw.replace('R', '.')
            try:
                val = float(raw)
            except (ValueError, TypeError):
                val = 0.0
            if val < 1:
                return f"{format_g(val)}pF"
            elif val < 1000:
                return f"{int(val)}pF" if val.is_integer() else f"{format_g(val)}pF"
            elif val < 1000000:
                val_nf = val / 1000.0
                return f"{int(val_nf)}nF" if val_nf.is_integer() else f"{format_g(val_nf)}nF"
            else:
                val_uf = val / 1000000.0
                return f"{int(val_uf)}uF" if val_uf.is_integer() else f"{format_g(val_uf)}uF"
        else:
            if len(raw) == 3 and raw.isdigit():
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val < 1000:
                    return f"{int(val)}pF" if val.is_integer() else f"{format_g(val)}pF"
                elif val < 1000000:
                    val_nf = val / 1000.0
                    return f"{int(val_nf)}nF" if val_nf.is_integer() else f"{format_g(val_nf)}nF"
                else:
                    val_uf = val / 1000000.0
                    return f"{int(val_uf)}uF" if val_uf.is_integer() else f"{format_g(val_uf)}uF"
            else:
                return raw


# =============================================================================
# Список правил для конденсаторов
# =============================================================================
def create_capacitor_rules():
    rules = []

    # 1. CCTC
    cctc_pattern = r'^TCC\s*(?P<size>\d{4})\s*(?P<dielectric>[A-Z0-9]+)\s*(?P<code>\d{3})\s*(?P<tolerance>[JKMZ])\s*(?P<voltage>\d{3})'
    cctc_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210'}
    cctc_dielectric = {'COG': 'C0G', 'X7R': 'X7R', 'X5R': 'X5R', 'X6S': 'X6S', 'X7T': 'X7T', 'Y5V': 'Y5V'}
    cctc_voltage = {'500': '50V', '250': '25V', '160': '16V', '100': '10V', '6R3': '6.3V', '630': '63V'}
    cctc_tolerance = {'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'}
    rules.append(VendorRule('CCTC', 'capacitor', cctc_pattern, cctc_size_map, dielectric_map=cctc_dielectric, voltage_map=cctc_voltage, tolerance_map=cctc_tolerance, is_resistor=False))

    # 2. KEMET
    kemet_pattern = r'^C(?P<size>\d{4})(?P<type>[A-Z])(?P<code>\d{3})(?P<tolerance>[BCDFGJKMOPZ])(?P<voltage>\d)(?P<dielectric>[GRPUV])(?P<suffix>[A-Z]{0,4})$'
    kemet_size_map = {'0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1812': '1812', '1825': '1825', '2220': '2220', '2225': '2225'}
    kemet_dielectric = {'G': 'C0G', 'R': 'X7R', 'P': 'X5R', 'U': 'Z5U', 'V': 'Y5V'}
    kemet_voltage = {'1': '100V', '2': '200V', '3': '25V', '4': '16V', '5': '50V', '6': '35V', '7': '4V', '8': '10V', '9': '6.3V'}
    kemet_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.5pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '+80%/-20%'}
    rules.append(VendorRule('KEMET', 'capacitor', kemet_pattern, kemet_size_map, kemet_dielectric, kemet_voltage, kemet_tolerance, None, None, False))

    # 3. TAIYO YUDEN
    taiyo_pattern = r'^(?P<voltage>[PALJETGUHQSX])(?P<series>[MVW])(?P<termination>[KS])(?P<size>\d{3})(?P<size_tolerance>[A-E]?)(?P<dielectric>BJ|B7|C6|C7|LD|CG|UJ|UK)(?P<code>\d+R\d+|\d{3})(?P<tolerance>[ABCDFGJKMZ])(?P<thickness>[A-Z])(?P<special>[A-Z]?)-?(?P<packaging>[FTPRW]?)(?P<internal>[A-Z]?)$'
    taiyo_size_map = {'021': '008004', '042': '01005', '063': '0201', '105': '0402', '107': '0603', '212': '0805', '316': '1206', '325': '1210', '432': '1812'}
    taiyo_dielectric = {'BJ': 'X5R', 'B7': 'X7R', 'C6': 'X6S', 'C7': 'X7S', 'LD': 'X5R', 'CG': 'C0G', 'UJ': 'U2J', 'UK': 'U2K'}
    taiyo_voltage = {'P': '2.5V', 'A': '4V', 'J': '6.3V', 'L': '10V', 'E': '16V', 'T': '25V', 'G': '35V', 'U': '50V', 'H': '100V', 'Q': '250V', 'S': '630V', 'X': '2000V'}
    rules.append(VendorRule('TaiyoYuden', 'capacitor', taiyo_pattern, taiyo_size_map, dielectric_map=taiyo_dielectric, voltage_map=taiyo_voltage, is_resistor=False))

    # 4. Murata
    dielectric_keys = ['X7R', 'X5R', 'X6S', 'X7S', 'X8R', 'Y5V', 'C0G', 'U2J', '5C', 'R7', 'R6', 'C7', 'R9', 'C8', 'R8', 'X6T', 'X5S', 'X7T', 'X8L', 'X8G', 'X8P', 'NP0', 'NPO']
    murata_pattern = r'^(?P<series>GRM|GJM|GQM|LLL|LLA|LLM|ERB|GCD|GCM|GCJ|GCH|GCE|GCQ|GMA|GNM|GR4|GR7|GA2|GA3|GC|GD|GF|GB)(?P<size>\d{2,3}[A-Z]?)(?P<dielectric>' + '|'.join(dielectric_keys) + r')(?P<voltage>[A-Z0-9]{2})(?P<code>\d{3})(?P<tolerance>[A-Z])(?P<rest>[A-Z0-9]*)$'
    murata_size_map = {
        '02': '01005', '03': '0201', '15': '0402', '18': '0603', '21': '0805', '31': '1206', '32': '1210', '43': '1812', '55': '2220',
        '022': '01005', '033': '0201', '155': '0402', '188': '0603', '216': '0805', '219': '0805', '316': '1206', '319': '1206', '329': '1210', '433': '1812', '555': '2220', '158': '0402',
        **{f'{code}{chr(c)}': size for code, size in [('15','0402'),('18','0603'),('21','0805'),('31','1206'),('32','1210'),('43','1812'),('55','2220')] for c in range(ord('A'), ord('Z')+1)}
    }
    murata_dielectric = {'5C': 'C0G', 'R7': 'X7R', 'R6': 'X5R', 'C7': 'X7S', 'U2J': 'U2J', 'X7R': 'X7R', 'X5R': 'X5R', 'X6S': 'X6S', 'X7S': 'X7S', 'X8R': 'X8R', 'Y5V': 'Y5V', 'C0G': 'C0G', 'R9': 'X7R', 'C8': 'X6S', 'R8': 'X8R', 'X6T': 'X6T', 'X5S': 'X5S', 'X7T': 'X7T', 'X8L': 'X8L', 'X8G': 'X8G', 'X8P': 'X8P', 'NP0': 'C0G', 'NPO': 'C0G'}
    murata_voltage = {'0G': '4V', '0J': '6.3V', '1A': '10V', '1C': '16V', '1E': '25V', '1H': '50V', '2A': '100V', '2D': '200V', '2E': '250V', '2H': '500V', '2J': '630V', '3A': '1kV', '3D': '2kV', '3F': '3.15kV', 'BB': '350V', 'E2': 'AC250V'}
    murata_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.5pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '+80%/-20%'}
    rules.append(VendorRule('Murata', 'capacitor', murata_pattern, murata_size_map, dielectric_map=murata_dielectric, voltage_map=murata_voltage, tolerance_map=murata_tolerance, is_resistor=False))

    # 5. Samsung
    samsung_cap_pattern = r'^CL(?P<size>\d{2})(?P<dielectric>[ACBXYZF])(?P<code>\d{3}|[0-9]R[0-9])(?P<tolerance>[BCDFGJKMZ])(?P<voltage>[A-Z])(?P<rest>.*)$'
    samsung_size_map = {'02': '01005', '03': '0201', '05': '0402', '10': '0603', '21': '0805', '31': '1206', '32': '1210', '42': '1808', '43': '1812', '55': '2220'}
    samsung_dielectric = {'C': 'C0G', 'A': 'X5R', 'B': 'X7R', 'X': 'X6S', 'F': 'Y5V', 'Y': 'X7S', 'Z': 'X7T'}
    samsung_voltage = {'R': '4V', 'Q': '6.3V', 'P': '10V', 'O': '16V', 'A': '25V', 'L': '35V', 'B': '50V', 'C': '100V', 'D': '200V', 'E': '250V', 'F': '350V', 'G': '500V', 'H': '630V', 'I': '1000V', 'J': '2000V', 'K': '3000V'}
    samsung_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'}
    rules.append(VendorRule('Samsung_Cap', 'capacitor', samsung_cap_pattern, samsung_size_map, samsung_dielectric, samsung_voltage, samsung_tolerance, None, None, False))

    # 6. TDK
    tdk_cap_pattern = r'^(?:C(?P<size>\d{4})|CGA(?P<cga_size>[2-8])[A-Z0-9]{1,2})(?P<dielectric>COG|C0G|X5R|X6S|X7R|X7S|X7T)(?P<voltage>0G|0J|1A|1C|1E|1V|1H|1N|2A|2E)(?P<code>\d{3})(?P<tolerance>[BCDFGJKM])(?P<rest>.*)$'
    tdk_size_map = {'0402': '01005', '0603': '0201', '1005': '0402', '1608': '0603', '2012': '0805', '3216': '1206', '3225': '1210', '4532': '1812', '5750': '2220', '2': '0402', '3': '0603', '4': '0805', '5': '1206', '6': '1210', '8': '1812'}
    tdk_dielectric = {'COG': 'C0G', 'C0G': 'C0G', 'X5R': 'X5R', 'X6S': 'X6S', 'X7R': 'X7R', 'X7S': 'X7S', 'X7T': 'X7T'}
    tdk_voltage = {'0G': '4V', '0J': '6.3V', '1A': '10V', '1C': '16V', '1E': '25V', '1V': '35V', '1H': '50V', '1N': '75V', '2A': '100V', '2E': '250V'}
    tdk_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%'}
    rules.append(VendorRule('TDK_Cap', 'capacitor', tdk_cap_pattern, tdk_size_map, tdk_dielectric, tdk_voltage, tdk_tolerance, None, None, False))

    # 7. AVX / Kyocera AVX
    avx_cap_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|1812|2220)(?P<voltage>[ZY3512V7])(?P<dielectric>[ACDFG])(?P<code>\d{3}|[0-9]R[0-9])(?P<tolerance>[BCDFGJKMZ])(?P<pack>[A-Z0-9]{3,4})$'
    avx_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1812': '1812', '2220': '2220'}
    avx_dielectric = {'A': 'C0G', 'C': 'X7R', 'D': 'X5R', 'F': 'X8R', 'G': 'Y5V'}
    avx_voltage = {'Z': '10V', 'Y': '16V', '3': '25V', '5': '50V', '1': '100V', '2': '200V', 'V': '250V', '7': '500V'}
    avx_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'}
    rules.append(VendorRule('AVX', 'capacitor', avx_cap_pattern, avx_size_map, dielectric_map=avx_dielectric, voltage_map=avx_voltage, tolerance_map=avx_tolerance, is_resistor=False))

    # 8. Walsin
    walsin_cap_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|1812)(?P<dielectric>[NBXSA])(?P<code>\d{3})(?P<tolerance>[ABCDFGJKMZ])(?P<voltage>\d{3})(?P<rest>.*)$'
    walsin_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1812': '1812'}
    walsin_dielectric = {'N': 'C0G', 'B': 'X7R', 'X': 'X5R', 'S': 'X6S', 'A': 'X7S'}
    walsin_voltage = {'040': '4V', '063': '6.3V', '100': '10V', '160': '16V', '250': '25V', '500': '50V'}
    walsin_tolerance = {'A': '0.05pF', 'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'}
    rules.append(VendorRule('Walsin_Cap', 'capacitor', walsin_cap_pattern, walsin_size_map, walsin_dielectric, walsin_voltage, walsin_tolerance, None, None, False))

    # 9. Yageo
    yageo_cap_pattern = r'^(?P<prefix>CC|AC|C|CQ)(?P<size>\d{4})(?P<tolerance>[BCDFGJKM])(?P<packing>[A-Z]{0,2})(?P<dielectric>X5R|X7R|X6S|X7S|X8R|X8G|COG|C0G|NP0|NPO|Y5V)(?P<voltage>[A-Z0-9]?)(?P<rest>[A-Z]{0,2})(?P<code>\d{3}|[0-9]R[0-9]{1,2})$'
    yageo_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1812': '1812', '2010': '2010', '2512': '2512'}
    yageo_dielectric = {'X5R': 'X5R', 'X7R': 'X7R', 'X6S': 'X6S', 'X7S': 'X7S', 'X8R': 'X8R', 'X8G': 'X8G', 'COG': 'C0G', 'C0G': 'C0G', 'NP0': 'C0G', 'NPO': 'C0G', 'Y5V': 'Y5V'}
    yageo_voltage = {'0': '100V', '4': '4V', '5': '6.3V', '6': '10V', '7': '16V', '8': '25V', '9': '50V', 'C': '100V', 'D': '200V', 'E': '250V', 'F': '350V', 'G': '500V', 'H': '630V', 'I': '1000V', 'J': '2000V', 'K': '3000V'}
    yageo_tolerance = {'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%'}
    rules.append(VendorRule('Yageo_Cap', 'capacitor', yageo_cap_pattern, yageo_size_map, dielectric_map=yageo_dielectric, voltage_map=yageo_voltage, tolerance_map=yageo_tolerance, is_resistor=False))

    return rules


# =============================================================================
# Список правил для резисторов
# =============================================================================
def create_resistor_rules():
    rules = []

    # 1. Vishay / Dale (серия CRCW)
    vishay_pattern = r'^CRCW(?P<size>0402|0603|0805|1206|1210|1218|2010|2512)(?P<code>\d{3,4}|\d+[RKM]\d*|0000)(?P<tolerance>[BDFJZN])(?P<tcr>[A-Z0-9]{1,2})(?P<pack>[A-Z]{2})$'
    vishay_size_map = {'0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'}
    vishay_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%', 'Z': '0%', 'N': '0%'}
    rules.append(VendorRule('Vishay', 'resistor', vishay_pattern, vishay_size_map, tolerance_map=vishay_tolerance, is_resistor=True))

    # 2. Panasonic (серия ERJ)
    panasonic_pattern = r'^ERJ-?(?P<size>1G|2G|2R|3G|3E|3R|6G|6E|6R|8G|8E|8R|14|12|1T)(?P<series>[A-Z]{0,2}?)(?:(?P<tolerance>[BDFGJKZ])|(?=[0-9R]))(?P<code>\d{3,4}|\d*R\d+|0R00)(?P<pack>[A-Z])$'
    panasonic_size_map = {'1G': '0201', '2G': '0402', '2R': '0402', '3G': '0603', '3E': '0603', '3R': '0603', '6G': '0805', '6E': '0805', '6R': '0805', '8G': '1206', '8E': '1206', '8R': '1206', '14': '1210', '12': '1812', '1T': '2512'}
    panasonic_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%', '0': '0%', '': '0%'}
    rules.append(VendorRule('Panasonic', 'resistor', panasonic_pattern, panasonic_size_map, tolerance_map=panasonic_tolerance, is_resistor=True))

    # 3. Bourns
    bourns_pattern = r'^(?P<series>CR|CRA|CRB|CHP|CMP)(?P<size>01005|0201|0402|0603|0805|1206|1210|2010|2512)-?(?P<tolerance>[BDFGJ])(?P<tcr>[A-Z/]{1,3})-?(?P<code>\d{3,4}|\d*R\d+|000)(?P<pack>[A-Z0-9]*)$'
    bourns_size_map = {'01005': '01005', '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '2010': '2010', '2512': '2512'}
    bourns_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Bourns', 'resistor', bourns_pattern, bourns_size_map, tolerance_map=bourns_tolerance, is_resistor=True))

    # 4. KOA Speer
    koa_pattern = r'^RK73(?P<type>[A-Z])(?P<size>1F|1H|1E|1J|2A|2B|2E|W2H|W3A)(?P<pack>[A-Z]{2,4})(?P<code>\d{3,4}|\d*R\d+|000|0)?(?P<tolerance>[BDFGJKZ])?$'
    koa_size_map = {'1F': '01005', '1H': '0201', '1E': '0402', '1J': '0603', '2A': '0805', '2B': '1206', '2E': '1210', 'W2H': '2010', 'W3A': '2512'}
    koa_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%', '': '0%'}
    rules.append(VendorRule('KOA_Speer', 'resistor', koa_pattern, koa_size_map, tolerance_map=koa_tolerance, is_resistor=True))

    # 5. Royal Ohm
    royal_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|2010|2512)(?P<power>[A-Z0-9]{2})(?P<tolerance>[BDFGJ])(?P<code>\d{3,4}|\d*R\d+|000)(?P<pack>[A-Z0-9]{3})$'
    royal_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '2010': '2010', '2512': '2512'}
    royal_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Royal_Ohm', 'resistor', royal_pattern, royal_size_map, tolerance_map=royal_tolerance, is_resistor=True))

    # 6. ROHM MCR
    rohm_mcr_pattern = r'^MCR(?P<size>006|01|03|10|18|25|50|100)(?P<pack>[A-Z]{3,4})(?P<tolerance>[BDFGJ])(?P<tcr>[A-Z0-9]?)(?P<code>\d{3,4}|\d*R\d+|000)$'
    rohm_mcr_size_map = {'006': '0201', '01': '0402', '03': '0603', '10': '0805', '18': '1206', '25': '1210', '50': '2010', '100': '2512'}
    rohm_mcr_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('ROHM_MCR', 'resistor', rohm_mcr_pattern, rohm_mcr_size_map, tolerance_map=rohm_mcr_tolerance, is_resistor=True))

    # 7. Viking
    viking_pattern = r'^CR-(?P<size>E5|01|02|03|05|06|10|0A|12|25|62)(?P<tolerance>[BDFJ])(?P<pack>[A-Z0-9]*?)-+(?P<value>[^\s]+)$'
    viking_size_map = {'E5': '01005', '01': '0201', '02': '0402', '03': '0603', '05': '0805', '06': '1206', '10': '1210', '0A': '2010', '12': '2512', '25': '1225', '62': '0612'}
    viking_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
    suffix_map_ohm = {'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ', 'L': 'mΩ'}
    rules.append(VendorRule('Viking', 'resistor', viking_pattern, viking_size_map, tolerance_map=viking_tolerance, suffix_map=suffix_map_ohm, is_resistor=True))

    # 8. Yageo RC
    rc_pattern = r'^RC(?P<size>\d{4})(?P<tolerance>[BDFJ])(?P<code>[\dR]{3,5})(?P<pack>[A-Z]{0,2})$'
    rc_size_map = {
        '0075': '01005', '0100': '0201', '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805',
        '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512',
        '1005': '0402', '1608': '0603', '2012': '0805', '3216': '1206', '3225': '1210', '5025': '2010', '6432': '2512'
    }
    rc_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}

    def rc_value_parser(raw: str) -> str:
        raw = raw.upper().strip()
        if raw in ('0000', '000', '00', '0', '0R', '0R0', '0R00') or (raw and all(c == '0' for c in raw)):
            return '0R'
        if 'R' in raw:
            val_str = raw.replace('R', '.')
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                return raw
            if val >= 1000000:
                return f"{format_g(val / 1000000)}M"
            elif val >= 1000:
                return f"{format_g(val / 1000)}K"
            else:
                return f"{format_g(val)}R"
        val = 0
        if len(raw) == 3 and raw.isdigit():
            try:
                mantissa = int(raw[:2])
                multiplier = int(raw[2])
                val = mantissa * (10 ** multiplier)
            except (ValueError, TypeError):
                return raw
        elif len(raw) == 4 and raw.isdigit():
            try:
                mantissa = int(raw[:3])
                multiplier = int(raw[3])
                val = mantissa * (10 ** multiplier)
            except (ValueError, TypeError):
                return raw
        elif len(raw) == 5 and raw.isdigit():
            try:
                mantissa = int(raw[:4])
                multiplier = int(raw[4])
                val = mantissa * (10 ** multiplier)
            except (ValueError, TypeError):
                return raw
        else:
            return raw

        if val > 0:
            if val >= 1000000:
                return f"{format_g(val / 1000000)}M"
            elif val >= 1000:
                return f"{format_g(val / 1000)}K"
            else:
                return f"{format_g(val)}R"
        else:
            return raw

    rules.append(VendorRule('RC_Yageo', 'resistor', rc_pattern, rc_size_map, tolerance_map=rc_tolerance, value_parser=rc_value_parser, is_resistor=True))

    # 9. HOTTECH RI
    ri_pattern = r'^RI(?P<size>\d{4})L(?P<code>[\dR]{3,5})(?P<tolerance>[BDFJ])T$'
    ri_size_map = {'0075': '01005', '0100': '0201', '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'}
    ri_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
    rules.append(VendorRule('RI_HOTTECH', 'resistor', ri_pattern, ri_size_map, tolerance_map=ri_tolerance, value_parser=rc_value_parser, is_resistor=True))

    # 10. ROHM ESR
    rohm_esr_pattern = r'^ESR(?P<size>01|03|10|18|25)(?P<pack>[A-Z]{3})(?P<tolerance>[DFJ])(?P<code>\d{3}|\d{4}|[0-9]R[0-9]{2})$'
    rohm_esr_size_map = {'01': '0402', '03': '0603', '10': '0805', '18': '1206', '25': '1210'}
    rohm_esr_tolerance = {'D': '0.5%', 'F': '1%', 'J': '5%'}
    rules.append(VendorRule('ROHM_ESR', 'resistor', rohm_esr_pattern, rohm_esr_size_map, tolerance_map=rohm_esr_tolerance, suffix_map=suffix_map_ohm, is_resistor=True))

    # 11. ROHM PMR
    rohm_pmr_pattern = r'^PMR(?P<size>01|03|10|18|25|50|100)(?P<pack>[A-Z]{3})(?P<tolerance>[FGJ])(?P<special>[UV]?)(?P<code>\d{1,2}L\d{0,2}|[0-9]{3})$'
    rohm_pmr_size_map = {'01': '0402', '03': '0603', '10': '0805', '18': '1206', '25': '1210', '50': '2010', '100': '2512'}
    rohm_pmr_tolerance = {'F': '1%', 'G': '2%', 'J': '5%'}

    def pmr_value_parser(raw: str) -> str:
        raw = raw.upper()
        if 'L' in raw:
            raw = raw.replace('L', '.')
            try:
                val_mohm = float(raw)
            except (ValueError, TypeError):
                return '?'
            val_ohm = val_mohm / 1000.0
            return f"{format_g(val_ohm)}R"
        else:
            return raw

    rules.append(VendorRule('ROHM_PMR', 'resistor', rohm_pmr_pattern, rohm_pmr_size_map, tolerance_map=rohm_pmr_tolerance, suffix_map={'L': 'mΩ'}, value_parser=pmr_value_parser, is_resistor=True))

    # 12. Samsung
    samsung_res_pattern = r'^(?P<prefix>RC|RCB|RF|RM|RN|RK|RP|RUT|RU|RUK|RJ|RCW|RCV|RCS|RFS|RPS|RH)(?P<size>\d{4})(?P<tolerance>[DFGJ])(?P<code>\d{3}|\d{4}|[0-9]R[0-9]{1,2})(?P<pack>[A-Z]{0,2})$'
    samsung_size_map_res = {'0402': '0402', '0603': '0603', '1005': '0402', '1608': '0603', '2012': '0805', '3216': '1206', '3225': '1210', '5025': '2010', '6432': '2512'}
    samsung_tolerance_res = {'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Samsung_Res', 'resistor', samsung_res_pattern, samsung_size_map_res, tolerance_map=samsung_tolerance_res, suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ'}, is_resistor=True))

    # 13. Walsin
    walsin_res_pattern = r'^(?P<prefix>WR|WW|WA|WT|WF|WK)(?P<size>\d{2})(?P<func>[A-Z]?)(?P<code>\d{3,4}|\d*R\d+)(?P<tolerance>[FJP]?)(?P<pack>[A-Z])(?P<term>[LGS])?$'
    walsin_size_map_res = {'01': '01005', '02': '0201', '04': '0402', '06': '0603', '08': '0805', '10': '1210', '12': '1206', '18': '1218', '20': '2010', '25': '2512'}
    walsin_tolerance_res = {'F': '1%', 'J': '5%', '': '0%'}
    rules.append(VendorRule('Walsin_Res', 'resistor', walsin_res_pattern, walsin_size_map_res, tolerance_map=walsin_tolerance_res, suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ', 'L': 'mΩ'}, is_resistor=True))

    # 14. Yageo (все серии)
    yageo_series = 'AC|RC|RT|RL|RV|RE|RA|RK|RS|RP|RQ|RN|RM|RJ'
    yageo_pattern = r'^(?P<series>' + yageo_series + r')(?P<size>\d{4})(?P<tolerance>[A-Z])(?P<pack>[A-Z]*)-?(?P<reel>\d{2})?(?P<value>\d+[RKM]\d*|\d{3,4}|0R00|0R0|0R|0000|000|00|0|\d+)L?$'
    yageo_size_map = {'0075': '0075', '0100': '0100', '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'}
    yageo_tolerance = {'B': '0.1%', 'C': '0.25%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%'}
    rules.append(VendorRule('Yageo', 'resistor', yageo_pattern, yageo_size_map, tolerance_map=yageo_tolerance, suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ'}, is_resistor=True))

    # 15. Российские Р1-12 и Р1-16
    def make_tolerance_map():
        base = {"0.05": "0.05%", "0.1": "0.1%", "0.25": "0.25%", "0.5": "0.5%", "1": "1%", "2": "2%", "5": "5%", "10": "10%", "20": "20%"}
        result = {}
        for k, v in base.items():
            result[k] = v
            result[k.replace('.', ',')] = v
            result[v] = v
            result[v.replace('.', ',')] = v
        return result

    rus_tol_map = make_tolerance_map()

    rus_p1_12_pattern = r'^[РPрp]1-12[- ](?P<size>[\d.,]+)[- ]+(?P<value>.+?)[- ]+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_12_size_map = {"0.062": "0402", "0,062": "0402", "0.063": "0603", "0,063": "0603", "0.1": "0603", "0,1": "0603", "0.10": "0603", "0,10": "0603", "0.125": "0805", "0,125": "0805", "0.25": "1206", "0,25": "1206", "0.33": "1210", "0,33": "1210", "0.5": "2010", "0,5": "2010", "0.75": "2512", "0,75": "2512", "1.0": "2512", "1,0": "2512", "1": "2512", "2.0": "4020", "2,0": "4020", "2": "4020"}
    rules.append(VendorRule('Rus_P1-12', 'resistor', rus_p1_12_pattern, rus_p1_12_size_map, tolerance_map=rus_tol_map, value_parser=parse_russian_resistor_value, is_resistor=True))

    rus_p1_16_pattern = r'^[РPрp]1-16[- ](?P<size>[\d.,]+)[- ]+(?P<value>.+?)[- ]+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_16_size_map = {"0.016": "0402", "0,016": "0402", "0.032": "0603", "0,032": "0603", "0.063": "0805", "0,063": "0805", "0.125": "1206", "0,125": "1206", "0.25": "2010", "0,25": "2010", "0.5": "2512", "0,5": "2512", "1.0": "4020", "1,0": "4020", "1": "4020"}
    rules.append(VendorRule('Rus_P1-16', 'resistor', rus_p1_16_pattern, rus_p1_16_size_map, tolerance_map=rus_tol_map, value_parser=parse_russian_resistor_value, is_resistor=True))

    return rules


_DEFAULT_PARSER = None

def get_default_parser() -> VendorParser:
    """Возвращает глобальный инициализированный экземпляр VendorParser."""
    global _DEFAULT_PARSER
    if _DEFAULT_PARSER is None:
        rules = create_capacitor_rules() + create_resistor_rules()
        _DEFAULT_PARSER = VendorParser(rules)
    return _DEFAULT_PARSER


def enable_high_dpi_awareness():
    """Включает поддержку High DPI (2K / 4K мониторы), устраняя размытие интерфейса."""
    try:
        # Windows 8.1+ Per-Monitor V2 / V1 DPI awareness
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Fallback for Windows Vista/7/8
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Вызываем при импорте модуля
enable_high_dpi_awareness()


# =============================================================================
# Дизайн-система THEMES (Dark Navy SaaS & Tech Slate Light)
# =============================================================================
THEMES = {
    "dark": {
        # Deep Dark Navy SaaS Palette (matching modern fintech/SaaS dashboard)
        "bg_app": "#0f172a",          # Основной фон рабочей зоны (глубокий тёмно-синий slate)
        "bg_sidebar": "#0f172a",      # Фон сайдбара сливается с рабочей зоной
        "bg_header": "#090d1a",       # Верхний хедер
        "bg_card": "#131e36",         # Контейнеры, карточки, панели
        "bg_card_inner": "#182644",   # Внутренние плашки и блоки
        "bg_input": "#111c33",        # Поля ввода и поиска
        "border": "#1e2f4f",          # Тонкие границы карточек
        "border_focus": "#38bdf8",    # Неоновый Sky Blue фокус
        "text_primary": "#f8fafc",    # Белый чёткий текст
        "text_secondary": "#94a3b8",  # Вторичный приглушенный сине-серый
        "text_header": "#7dd3fc",     # Мягкий голубой для колонок и шапки
        "text_muted": "#64748b",      # Мягкий серый
        "accent": "#0ea5e9",          # Sky Blue (основной акцент кнопок и пилюль)
        "accent_hover": "#38bdf8",    # Светло-голубой при наведении
        "accent_active": "#0284c7",   # Нажатие
        "accent_text": "#ffffff",     # Белый текст
        "btn_sec_bg": "#1e2f4f",      # Вторичные кнопки (тёмно-синий)
        "btn_sec_fg": "#e2e8f0",      # Текст вторичных кнопок
        "btn_sec_hover": "#2b4169",   # Наведение вторичных кнопок
        "nav_active_bg": "#1e2f4f",   # Активная плашка сайдбара
        "nav_active_border": "#38bdf8",# Неоновая полоска слева
        "badge_res_bg": "#0c4a6e",
        "badge_res_fg": "#7dd3fc",
        "badge_cap_bg": "#2e1065",
        "badge_cap_fg": "#c084fc",
        "badge_vendor_bg": "#1e3a8a",
        "badge_vendor_fg": "#60a5fa",
        "success_bg": "#064e3b",
        "success_fg": "#34d399",      # Изумрудный зелёный
        "error_bg": "#4c0519",
        "error_fg": "#f43f5e",        # Яркий розово-красный
        "warning_bg": "#451a03",
        "warning_fg": "#fbbf24",      # Золотисто-янтарный
        "status_bg": "#131e36",
        "tree_bg": "#131e36",         # Таблицы данных
        "tree_fg": "#f8fafc",
        "tree_head_bg": "#0c1527",    # Заголовки таблиц
        "tree_head_fg": "#7dd3fc",    # Голубые заголовки колонок
        "tree_sel_bg": "#0369a1",     # Выделение строк (глубокий голубой)
        "tree_sel_fg": "#ffffff",
        "row_odd": "#0e182e",         # Полосатые строки таблицы
        "row_even": "#131e36",
        "scroll_trough": "#0e182e",   # Полосы прокрутки
        "scroll_thumb": "#1e2f4f",
        "scroll_thumb_hover": "#2b4169",
        "scroll_thumb_active": "#0ea5e9",
        "scroll_arrow": "#64748b",
        "is_dark": True
    },
    "light": {
        # Modern Tech Slate Light Palette (Linear / Apple Pro / Stripe inspired)
        "bg_app": "#f8fafc",          # Мягкий сланец Slate-50 (исключает эффект 'белого листа')
        "bg_sidebar": "#f1f5f9",      # Структурный Slate-100 для навигации
        "bg_header": "#ffffff",       # Чистый белый верхний хедер
        "bg_card": "#ffffff",         # Чистые белые контрастные карточки
        "bg_card_inner": "#f1f5f9",   # Подложки блоков и внутренних карточек
        "bg_input": "#ffffff",        # Поля ввода
        "border": "#e2e8f0",          # Мягкие разделители Slate-200
        "border_focus": "#2563eb",    # Кобальтовый фокус ввода
        "text_primary": "#0f172a",    # Глубокий сланец (WCAG AAA, без резкости #000)
        "text_secondary": "#475569",  # Четкий средний серый (Slate-600)
        "text_header": "#1e3a8a",     # Благородный темно-синий для акцентных заголовков
        "text_muted": "#64748b",      # Мягкий серый для сносок и подсказок
        "accent": "#1d4ed8",          # Кобальтовый синий (WCAG AAA на белом тексте)
        "accent_hover": "#1e40af",    # Темно-синий при наведении
        "accent_active": "#172554",   # Глубокий синий при нажатии
        "accent_text": "#ffffff",     # Белый текст кнопок
        "btn_sec_bg": "#f1f5f9",      # Вторичная кнопка (Slate-100)
        "btn_sec_fg": "#0f172a",      # Текст вторичной кнопки
        "btn_sec_hover": "#e2e8f0",   # Наведение вторичной кнопки (Slate-200)
        "nav_active_bg": "#e2e8f0",   # Активная плашка сайдбара
        "nav_active_border": "#1d4ed8",# Синяя полоска активного пункта
        "badge_res_bg": "#e0f2fe",    # Пастельный Sky-100 для резисторов
        "badge_res_fg": "#0369a1",    # Контрастный Sky-700
        "badge_cap_bg": "#f3e8ff",    # Пастельный Purple-100 для конденсаторов
        "badge_cap_fg": "#7e22ce",    # Контрастный Purple-700
        "badge_vendor_bg": "#dbeafe", # Пастельный Blue-100 для производителей
        "badge_vendor_fg": "#1d4ed8", # Контрастный Blue-700
        "success_bg": "#dcfce7",      # Emerald-100
        "success_fg": "#15803d",      # Emerald-700
        "error_bg": "#fee2e2",        # Red-100
        "error_fg": "#b91c1c",        # Red-700
        "warning_bg": "#fef3c7",      # Amber-100
        "warning_fg": "#b45309",      # Amber-700
        "status_bg": "#ffffff",       # Статус-бар
        "tree_bg": "#ffffff",         # Таблицы данных
        "tree_fg": "#0f172a",         # Текст таблиц
        "tree_head_bg": "#f1f5f9",    # Шапка колонок таблиц
        "tree_head_fg": "#1e293b",    # Текст заголовков колонок
        "tree_sel_bg": "#dbeafe",     # Пастельное выделение строк
        "tree_sel_fg": "#0f172a",     # Текст выделенной строки
        "row_odd": "#f8fafc",         # Зебра нечетных строк (мягкий сланец)
        "row_even": "#ffffff",        # Зебра четных строк (белый)
        "scroll_trough": "#f1f5f9",   # Трек скроллбара
        "scroll_thumb": "#cbd5e1",    # Ползунок скроллбара (Slate-300)
        "scroll_thumb_hover": "#94a3b8", # Ползунок при наведении (Slate-400)
        "scroll_thumb_active": "#1d4ed8",# Ползунок при перетаскивании
        "scroll_arrow": "#64748b",    # Стрелки скроллбара
        "is_dark": False
    }
}


def get_settings_path() -> str:
    """Возвращает путь к файлу настроек settings.json в %APPDATA%\\SMD_Hub."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    cfg_dir = os.path.join(appdata, "SMD_Hub")
    try:
        os.makedirs(cfg_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(cfg_dir, "settings.json")


def get_saved_theme() -> str:
    """Возвращает сохраненную тему оформления ('dark' или 'light'). По умолчанию 'dark'."""
    try:
        path = get_settings_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                theme = data.get("theme", "dark")
                if theme in THEMES:
                    return theme
    except Exception:
        pass
    return "dark"


def set_saved_theme(theme_name: str):
    """Сохраняет выбранную тему оформления в settings.json."""
    if theme_name not in THEMES:
        theme_name = "dark"
    try:
        path = get_settings_path()
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["theme"] = theme_name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Warning: could not save theme setting:", e)


def restart_application(root: tk.Tk = None):
    """
    Выполняет чистый безопасный перезапуск текущего приложения
    для надежного применения выбранной темы без конфликтов стилей.
    Корректно работает как в Python, так и в собранных .EXE (PyInstaller --onefile).
    """
    clean_env = os.environ.copy()
    clean_env.pop('_MEIPASS2', None)
    clean_env.pop('_MEIPASS', None)

    is_frozen = getattr(sys, 'frozen', False)
    exe_path = sys.executable

    try:
        if is_frozen:
            subprocess.Popen([exe_path] + sys.argv[1:], env=clean_env)
        else:
            subprocess.Popen([exe_path] + sys.argv, env=clean_env)
    except Exception as e:
        print("Error restarting application:", e)

    if root:
        try:
            root.destroy()
        except Exception:
            pass
    sys.exit(0)


def get_system_theme() -> str:
    """Возвращает активную тему оформления (из настроек)."""
    return get_saved_theme()


def set_window_titlebar_theme(root: Union[tk.Tk, tk.Toplevel], is_dark: bool = True):
    """
    Применяет тёмную или светлую тему к нативному заголовку окна Windows 10/11 через DWM API.
    Атрибуты: 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 11), 19 = Windows 10 (билд 18985+).
    """
    try:
        root.update_idletasks()
        hwnd = root.winfo_id()
        parent_hwnd = ctypes.windll.user32.GetParent(hwnd)
        target_hwnd = parent_hwnd if parent_hwnd else hwnd

        val_int = ctypes.c_int(1 if is_dark else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win11), 19 = Win10
        for h in (target_hwnd, hwnd):
            if not h:
                continue
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        h, attr, ctypes.byref(val_int), ctypes.sizeof(val_int)
                    )
                except Exception:
                    pass

            # 35 = DWMWA_CAPTION_COLOR (Win11 build 22000+)
            # COLORREF 0x00BBGGRR -> dark: #090d1a -> 0x001a0d09; light: #ffffff -> 0x00ffffff
            try:
                caption_color = ctypes.c_uint32(0x001a0d09 if is_dark else 0x00ffffff)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    h, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color)
                )
            except Exception:
                pass
    except Exception:
        pass


def apply_ttk_theme(style: ttk.Style, theme_name: str = "dark"):
    """Настраивает стили TTK для переданной темы с использованием движка 'clam'."""
    t = THEMES[theme_name]

    try:
        style.theme_use('clam')
    except Exception:
        pass

    # Стиль скрытых вкладок для мастера шагов
    style.layout("Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    style.layout("Hidden.TNotebook.Tab", [])

    # Базовые фреймы и карточки
    style.configure("TFrame", background=t["bg_app"])
    style.configure("Card.TFrame", background=t["bg_card"], relief="flat")
    style.configure("InnerCard.TFrame", background=t["bg_card_inner"], relief="flat")
    
    # Текстовые метки
    style.configure("TLabel", background=t["bg_app"], foreground=t["text_primary"], font=("Segoe UI", 9))
    style.configure("Card.TLabel", background=t["bg_card"], foreground=t["text_primary"], font=("Segoe UI", 9))
    style.configure("InnerCard.TLabel", background=t["bg_card_inner"], foreground=t["text_primary"], font=("Segoe UI", 9))
    style.configure("Muted.TLabel", foreground=t["text_muted"], font=("Segoe UI", 8))
    style.configure("Header.TLabel", foreground=t["text_header"], font=("Segoe UI", 12, "bold"))
    
    # Группы полей (LabelFrame)
    style.configure("TLabelframe", background=t["bg_app"], foreground=t["accent"], relief="groove", borderwidth=1)
    style.configure("TLabelframe.Label", background=t["bg_app"], foreground=t["accent"], font=("Segoe UI", 9, "bold"))
    style.configure("Card.TLabelframe", background=t["bg_card"], foreground=t["accent"], relief="groove", borderwidth=1)
    style.configure("Card.TLabelframe.Label", background=t["bg_card"], foreground=t["accent"], font=("Segoe UI", 9, "bold"))

    # Кнопки
    style.configure("TButton",
                    background=t["btn_sec_bg"],
                    foreground=t["btn_sec_fg"],
                    font=("Segoe UI", 9),
                    borderwidth=1,
                    focuscolor="none",
                    padding=[10, 5])
    style.map("TButton",
              background=[("pressed", t["accent"]), ("active", t["btn_sec_hover"]), ("disabled", t["bg_input"])],
              foreground=[("pressed", t["accent_text"]), ("active", t["text_primary"]), ("disabled", t["text_muted"])],
              bordercolor=[("active", t["border_focus"])])

    style.configure("Accent.TButton",
                    background=t["accent"],
                    foreground=t["accent_text"],
                    font=("Segoe UI", 9, "bold"),
                    borderwidth=0,
                    focuscolor="none",
                    padding=[12, 6])
    style.map("Accent.TButton",
              background=[("pressed", t["accent_active"]), ("active", t["accent_hover"])],
              foreground=[("active", t["accent_text"])])

    style.configure("Success.TButton",
                    background="#059669",
                    foreground="#ffffff",
                    font=("Segoe UI", 9, "bold"),
                    borderwidth=0,
                    focuscolor="none",
                    padding=[12, 6])
    style.map("Success.TButton",
              background=[("active", "#10b981"), ("pressed", "#047857")],
              foreground=[("active", "#ffffff")])

    # Поля ввода (Entry)
    style.configure("TEntry",
                    fieldbackground=t["bg_input"],
                    foreground=t["text_primary"],
                    insertcolor=t["text_primary"],
                    bordercolor=t["border"],
                    lightcolor=t["border"],
                    darkcolor=t["border"],
                    padding=5)
    style.map("TEntry",
              bordercolor=[("focus", t["border_focus"])],
              fieldbackground=[("disabled", t["btn_sec_bg"])],
              foreground=[("disabled", t["text_muted"])])

    # Выпадающие списки (Combobox)
    style.configure("TCombobox",
                    fieldbackground=t["bg_input"],
                    background=t["btn_sec_bg"],
                    foreground=t["text_primary"],
                    arrowcolor=t["text_header"],
                    bordercolor=t["border"],
                    padding=5)
    style.map("TCombobox",
              fieldbackground=[("readonly", t["bg_input"])],
              selectbackground=[("readonly", t["accent"])],
              selectforeground=[("readonly", t["accent_text"])],
              bordercolor=[("focus", t["border_focus"])])

    # Таблицы данных (Treeview)
    style.configure("Treeview",
                    background=t["tree_bg"],
                    foreground=t["tree_fg"],
                    fieldbackground=t["tree_bg"],
                    font=("Segoe UI", 9),
                    rowheight=26,
                    borderwidth=1,
                    relief="solid")
    style.map("Treeview",
              background=[("selected", t["tree_sel_bg"])],
              foreground=[("selected", t["tree_sel_fg"])])
    style.configure("Treeview.Heading",
                    background=t["tree_head_bg"],
                    foreground=t["tree_head_fg"],
                    font=("Segoe UI", 9, "bold"),
                    relief="flat",
                    padding=6)
    style.map("Treeview.Heading",
              background=[("active", t["btn_sec_hover"])])

    # Вкладки (Notebook)
    style.configure("TNotebook", background=t["bg_app"], borderwidth=0, tabmargins=[2, 5, 2, 0])
    style.configure("TNotebook.Tab",
                    background=t["btn_sec_bg"],
                    foreground=t["btn_sec_fg"],
                    font=("Segoe UI", 9),
                    padding=[16, 7],
                    borderwidth=1)
    style.map("TNotebook.Tab",
              background=[("selected", t["accent"]), ("active", t["btn_sec_hover"])],
              foreground=[("selected", t["accent_text"]), ("active", t["text_primary"])])

    # Стилизация полос прокрутки (Scrollbar) под тему
    for sb_name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(sb_name,
                        gripcount=0,
                        background=t["scroll_thumb"],
                        darkcolor=t["scroll_trough"],
                        lightcolor=t["scroll_trough"],
                        troughcolor=t["scroll_trough"],
                        bordercolor=t["scroll_trough"],
                        arrowcolor=t["scroll_arrow"],
                        arrowsize=11)
        style.map(sb_name,
                  background=[("active", t["scroll_thumb_hover"]), ("pressed", t["scroll_thumb_active"])],
                  arrowcolor=[("active", t["text_primary"]), ("pressed", t["text_primary"])])

    # Чекбоксы (неоновый Sky Blue статус при выборе с белой галочкой)
    style.configure("TCheckbutton",
                    background=t["bg_app"],
                    foreground=t["text_primary"],
                    indicatorcolor="#ffffff",
                    indicatorbackground=t["bg_input"],
                    indicatormargin=[1, 1, 4, 1],
                    focuscolor="",
                    font=("Segoe UI", 9))
    style.map("TCheckbutton",
              background=[("active", t["bg_app"]), ("pressed", t["bg_app"]), ("!disabled", t["bg_app"])],
              foreground=[("active", t["text_primary"]), ("pressed", t["text_primary"]), ("!disabled", t["text_primary"])],
              indicatorcolor=[("selected", "#ffffff"), ("pressed", "#ffffff"), ("!selected", t["bg_input"])],
              indicatorbackground=[("selected", t["accent"]), ("active", t["bg_card_inner"]), ("!disabled", t["bg_input"])])

    style.configure("Card.TCheckbutton",
                    background=t["bg_card"],
                    foreground=t["text_primary"],
                    indicatorcolor="#ffffff",
                    indicatorbackground=t["bg_input"],
                    indicatormargin=[1, 1, 4, 1],
                    focuscolor="",
                    font=("Segoe UI", 9))
    style.map("Card.TCheckbutton",
              background=[("active", t["bg_card"]), ("pressed", t["bg_card"]), ("!disabled", t["bg_card"])],
              foreground=[("active", t["text_primary"]), ("pressed", t["text_primary"]), ("!disabled", t["text_primary"])],
              indicatorcolor=[("selected", "#ffffff"), ("pressed", "#ffffff"), ("!selected", t["bg_input"])],
              indicatorbackground=[("selected", t["accent"]), ("active", t["bg_card_inner"]), ("!disabled", t["bg_input"])])

    # Радиокнопки (яркая Sky Blue кнопка с белой контрастной точкой при выборе)
    style.configure("TRadiobutton",
                    background=t["bg_app"],
                    foreground=t["text_primary"],
                    indicatorforeground="#ffffff",
                    indicatorbackground=t["bg_input"],
                    indicatormargin=[1, 1, 4, 1],
                    focuscolor="",
                    font=("Segoe UI", 9))
    style.map("TRadiobutton",
              background=[("active", t["bg_app"]), ("pressed", t["bg_app"]), ("!disabled", t["bg_app"])],
              foreground=[("active", t["text_primary"]), ("pressed", t["text_primary"]), ("!disabled", t["text_primary"])],
              indicatorforeground=[("selected", "#ffffff"), ("pressed", "#ffffff"), ("!selected", t["bg_input"])],
              indicatorbackground=[("selected", t["accent"]), ("active", t["bg_card_inner"]), ("!disabled", t["bg_input"])])

    style.configure("Card.TRadiobutton",
                    background=t["bg_card"],
                    foreground=t["text_primary"],
                    indicatorforeground="#ffffff",
                    indicatorbackground=t["bg_input"],
                    indicatormargin=[1, 1, 4, 1],
                    focuscolor="",
                    font=("Segoe UI", 9))
    style.map("Card.TRadiobutton",
                    background=[("active", t["bg_card"]), ("pressed", t["bg_card"]), ("!disabled", t["bg_card"])],
                    foreground=[("active", t["text_primary"]), ("pressed", t["text_primary"]), ("!disabled", t["text_primary"])],
                    indicatorforeground=[("selected", "#ffffff"), ("pressed", "#ffffff"), ("!selected", t["bg_input"])],
                    indicatorbackground=[("selected", t["accent"]), ("active", t["bg_card_inner"]), ("!disabled", t["bg_input"])])


def style_widget_tree(widget, theme_name: str = None, parent_bg=None):
    """
    Рекурсивно обходит всё дерево Tkinter виджетов и настраивает фоновые цвета,
    текст, кнопки, списки, поля ввода и холсты в соответствии с выбранной темой.
    """
    if theme_name is None:
        theme_name = get_saved_theme()
    if theme_name not in THEMES:
        theme_name = "dark"
    t = THEMES[theme_name]
    bg = parent_bg or t["bg_app"]

    w_type = widget.winfo_class()

    try:
        if w_type in ("Frame", "Toplevel", "Tk"):
            # Проверяем, не является ли это специальной карточкой или сайдбаром
            cur_bg = widget.cget("bg")
            if cur_bg in (t["bg_card"], THEMES["dark"]["bg_card"], THEMES["light"]["bg_card"]):
                bg = t["bg_card"]
            elif cur_bg in (t["bg_card_inner"], THEMES["dark"]["bg_card_inner"], THEMES["light"]["bg_card_inner"]):
                bg = t["bg_card_inner"]
            elif cur_bg in (t["bg_sidebar"], THEMES["dark"]["bg_sidebar"], THEMES["light"]["bg_sidebar"]):
                bg = t["bg_sidebar"]
            elif cur_bg in (t["bg_header"], THEMES["dark"]["bg_header"], THEMES["light"]["bg_header"]):
                bg = t["bg_header"]
            else:
                bg = parent_bg or t["bg_app"]
            widget.configure(bg=bg)
            if w_type == "Toplevel":
                set_window_titlebar_theme(widget, is_dark=t["is_dark"])

        elif w_type == "Canvas":
            bg = parent_bg or t["bg_app"]
            widget.configure(bg=bg, highlightthickness=0)

        elif w_type == "Label":
            lbl_txt = str(widget.cget("text"))
            if "Двойной клик" in lbl_txt or "Двойной щелчок" in lbl_txt:
                widget.configure(bg=t["badge_res_bg"], fg=t["badge_res_fg"], relief="flat")
            else:
                # Не перетираем специальные бейджи и акцентные заголовки
                cur_fg = widget.cget("fg")
                preserve_fgs = (
                    t["accent"], t["text_header"], t["text_muted"], t["text_secondary"],
                    t["success_fg"], t["error_fg"], t["warning_fg"],
                    t["badge_res_fg"], t["badge_cap_fg"], t["badge_vendor_fg"],
                    THEMES["dark"]["badge_res_fg"], THEMES["dark"]["badge_cap_fg"], THEMES["dark"]["badge_vendor_fg"],
                    THEMES["light"]["badge_res_fg"], THEMES["light"]["badge_cap_fg"], THEMES["light"]["badge_vendor_fg"]
                )
                if cur_fg not in preserve_fgs:
                    widget.configure(fg=t["text_primary"])
                widget.configure(bg=parent_bg or t["bg_app"])

        elif w_type == "Labelframe":
            widget.configure(bg=parent_bg or t["bg_app"], fg=t["accent"], highlightbackground=t["border"], relief="groove")

        elif w_type == "Button":
            btn_text = widget.cget("text")
            cur_bg = str(widget.cget("bg")).lower()
            # Сохраняем кастомные акцентные/зеленые/красные кнопки
            if cur_bg in (t["accent"].lower(), "#059669", "#047857", "#10b981", "#23a55a", "#4caf50", "#7f1d1d", "#991b1b", "#dc2626", "#2563eb", "#0284c7"):
                pass
            elif any(k in btn_text for k in ("✅", "🚀", "Загрузить новый", "Сформировать", "Запустить", "Применить правила", "Объединить и сохранить")):
                widget.configure(bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                                 activeforeground=t["accent_text"], relief="flat", bd=0)
            elif "Очистка" in btn_text or "Сбросить" in btn_text:
                widget.configure(bg=t["btn_sec_bg"], fg=t["text_muted"], activebackground=t["btn_sec_hover"],
                                 activeforeground=t["text_primary"], relief="flat", bd=0)
            else:
                widget.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                                 activeforeground=t["text_primary"], relief="flat", bd=0)

        elif w_type == "Entry":
            widget.configure(bg=t["bg_input"], fg=t["text_primary"], insertbackground=t["text_primary"],
                             relief="flat", highlightthickness=1, highlightbackground=t["border"], highlightcolor=t["border_focus"])

        elif w_type == "Listbox":
            widget.configure(bg=t["bg_input"], fg=t["text_primary"], selectbackground=t["accent"],
                             selectforeground=t["accent_text"], relief="flat", highlightthickness=1,
                             highlightbackground=t["border"])

        elif w_type == "Text":
            widget.configure(bg=t["bg_input"], fg=t["text_primary"], insertbackground=t["text_primary"],
                             relief="flat", highlightthickness=1, highlightbackground=t["border"])

        elif w_type in ("Checkbutton", "Radiobutton"):
            widget.configure(bg=parent_bg or t["bg_app"], fg=t["text_primary"],
                             activebackground=parent_bg or t["bg_app"], activeforeground=t["text_primary"],
                             selectcolor=t["accent"])

        elif "treeview" in w_type.lower():
            try:
                widget.tag_configure('odd', background=t["row_odd"], foreground=t["tree_fg"])
                widget.tag_configure('even', background=t["row_even"], foreground=t["tree_fg"])
                widget.tag_configure('oddrow', background=t["row_odd"], foreground=t["tree_fg"])
                widget.tag_configure('evenrow', background=t["row_even"], foreground=t["tree_fg"])
                widget.tag_configure('selected', background=t["tree_sel_bg"], foreground=t["tree_sel_fg"])
            except Exception:
                pass
    except Exception:
        pass

    # Рекурсивный проход по всем потомкам
    for child in widget.winfo_children():
        style_widget_tree(child, theme_name, parent_bg=bg)


def create_styled_toplevel(
    parent,
    title: str,
    geometry: Optional[str] = None,
    min_size: Optional[Union[Tuple[int, int], str]] = None,
    theme_name: Optional[str] = None
) -> tk.Toplevel:
    """
    Создает Toplevel окно с правильной темой (адаптивный заголовок Windows DWM,
    фон в тон активной темы, минимальные размеры и умная прокрутка колесом мыши).
    
    Защита: если по ошибке тема оформления передана в min_size (как строка 'dark'/'light'),
    она автоматически распознаётся как theme_name без падения приложения.
    """
    # Защитная автокоррекция порядка аргументов
    if isinstance(min_size, str):
        if theme_name is None:
            theme_name = min_size
        min_size = None

    if theme_name is None:
        theme_name = get_saved_theme()
    if theme_name not in THEMES:
        theme_name = "dark"

    win = tk.Toplevel(parent)
    win.title(title)
    if geometry:
        win.geometry(geometry)

    # Применение минимальных размеров
    if min_size and isinstance(min_size, (tuple, list)) and len(min_size) >= 2:
        try:
            win.minsize(int(min_size[0]), int(min_size[1]))
        except Exception:
            pass
    elif geometry and "x" in geometry:
        try:
            w, h = map(int, geometry.split("+")[0].split("-")[0].split("x"))
            win.minsize(min(w, 400), min(h, 200))
        except Exception:
            pass

    t = THEMES[theme_name]
    win.configure(bg=t["bg_app"])
    is_dark = t["is_dark"]
    set_window_titlebar_theme(win, is_dark=is_dark)
    win.after(25, lambda: set_window_titlebar_theme(win, is_dark=is_dark))
    enable_smooth_mousewheel(win)
    return win



# =============================================================================
# Интерактивные всплывающие подсказки ToolTip
# =============================================================================
class ToolTip:
    """Всплывающая подсказка при наведении курсора на виджет."""
    def __init__(self, widget, text, delay_ms=400):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window = None
        self.after_id = None
        
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay_ms, self._show_tip)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide_tip()

    def _cancel(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show_tip(self):
        """Отображает всплывающее окно подсказки с защитой от уничтожения родительского виджета."""
        if self.tip_window or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
            x = x + self.widget.winfo_rootx() + 20
            y = y + self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            
            frame = tk.Frame(tw, background="#111214", highlightbackground="#5865f2", highlightthickness=1, padx=8, pady=5)
            frame.pack()
            label = tk.Label(
                frame, text=self.text, justify=tk.LEFT, background="#111214", foreground="#f2f3f5",
                font=("Segoe UI", 8), wraplength=350
            )
            label.pack()
        except Exception:
            self.tip_window = None

    def _hide_tip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass


# =============================================================================
# Универсальная умная прокрутка колесом мыши (MouseWheel)
# =============================================================================
def enable_smooth_mousewheel(root_or_window):
    """
    Привязывает глобальную умную прокрутку колесом мыши ко всему окну / телу приложения.
    Правило работы:
    1. Если курсор мыши находится над таблицей (Treeview) или списком (Listbox/Text),
       прокручивается сам этот список/таблица.
    2. Если курсор находится в любом другом месте тела программы (фон, карточки, метки,
       кнопки, чекбоксы, рамки), автоматически находится активный Canvas окна
       и плавно прокручивается рабочая область.
    """
    def _search_canvas_recursive(w):
        try:
            if w.winfo_class() == "Canvas" and w.winfo_viewable():
                return w
            for child in w.winfo_children():
                found = _search_canvas_recursive(child)
                if found:
                    return found
        except Exception:
            pass
        return None

    def _find_canvas(widget):
        curr = widget
        while curr is not None:
            try:
                if curr.winfo_class() == "Canvas":
                    return curr
                curr = getattr(curr, "master", None)
            except Exception:
                break
        try:
            top = widget.winfo_toplevel()
            return _search_canvas_recursive(top)
        except Exception:
            return None

    def _on_mousewheel(event):
        try:
            widget = event.widget
            w_class = widget.winfo_class()

            # Если мышь над Treeview или Listbox — прокручиваем сам список
            if w_class in ("Treeview", "Listbox", "Text"):
                try:
                    delta = event.delta
                    if delta:
                        units = int(-1 * (delta / 120))
                        widget.yview_scroll(units, "units")
                        return "break"
                except Exception:
                    pass
                return

            # Иначе прокручиваем основной Canvas окна/вкладки
            canvas = _find_canvas(widget)
            if canvas and canvas.winfo_exists():
                bbox = canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                canvas_h = canvas.winfo_height()

                if content_h > canvas_h + 2:
                    delta = event.delta
                    if delta:
                        scroll_units = int(-1 * (delta / 120)) * 2
                        canvas.yview_scroll(scroll_units, "units")
                        return "break"
        except Exception:
            pass

    def _on_mousewheel_linux(event, units: int):
        try:
            widget = event.widget
            w_class = widget.winfo_class()
            if w_class in ("Treeview", "Listbox", "Text"):
                try:
                    widget.yview_scroll(units, "units")
                    return "break"
                except Exception:
                    pass
                return

            canvas = _find_canvas(widget)
            if canvas and canvas.winfo_exists():
                bbox = canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                canvas_h = canvas.winfo_height()
                if content_h > canvas_h + 2:
                    canvas.yview_scroll(units * 2, "units")
                    return "break"
        except Exception:
            pass

    try:
        root_or_window.bind_all("<MouseWheel>", _on_mousewheel)
        root_or_window.bind_all("<Button-4>", lambda e: _on_mousewheel_linux(e, -1))
        root_or_window.bind_all("<Button-5>", lambda e: _on_mousewheel_linux(e, 1))
    except Exception:
        pass


def show_faq_dialog(parent, current_theme="dark"):
    t = THEMES[current_theme]
    dialog = tk.Toplevel(parent)
    dialog.title("📖 Руководство оператора и FAQ — SMD Hub")
    dialog.geometry("1140x820")
    dialog.minsize(920, 600)
    dialog.resizable(True, True)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(bg=t["bg_app"])
    set_window_titlebar_theme(dialog, t["is_dark"])

    # Центрирование окна
    dialog.update_idletasks()
    try:
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 1140
        h = 820
        x = max(10, px + (pw - w) // 2)
        y = max(10, py + (ph - h) // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

    # Хедер диалога с поиском и кнопками
    header = tk.Frame(dialog, bg=t["bg_card"], padx=15, pady=10)
    header.pack(fill=tk.X)

    title_frame = tk.Frame(header, bg=t["bg_card"])
    title_frame.pack(side=tk.LEFT, fill=tk.Y)

    lbl_title = tk.Label(
        title_frame,
        text="📖 Руководство оператора и FAQ — SMD Hub",
        font=("Segoe UI", 12, "bold"),
        bg=t["bg_card"],
        foreground=t["text_primary"]
    )
    lbl_title.pack(side=tk.LEFT)

    # Панель быстрого поиска по тексту справки
    search_frame = tk.Frame(header, bg=t["bg_card"])
    search_frame.pack(side=tk.RIGHT, padx=(10, 0))

    btn_close = ttk.Button(search_frame, text="Закрыть", command=dialog.destroy)
    btn_close.pack(side=tk.RIGHT, padx=(10, 0))

    match_lbl = tk.Label(search_frame, text="", font=("Segoe UI", 9), bg=t["bg_card"], fg="#94a3b8")
    match_lbl.pack(side=tk.RIGHT, padx=5)

    btn_clear_search = ttk.Button(search_frame, text="✕", width=3)
    btn_clear_search.pack(side=tk.RIGHT, padx=2)

    search_entry = ttk.Entry(search_frame, width=24)
    search_entry.pack(side=tk.RIGHT, padx=5)

    tk.Label(search_frame, text="🔍 Поиск:", font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg="#93c5fd").pack(side=tk.RIGHT)

    # Текстовое поле с прокруткой для отображения руководства
    text_container = tk.Frame(dialog, bg=t["bg_app"], padx=10, pady=10)
    text_container.pack(fill=tk.BOTH, expand=True)

    txt = tk.Text(
        text_container,
        wrap=tk.WORD,
        font=("Segoe UI", 10),
        bg="#0b1329" if t["is_dark"] else "#ffffff",
        fg="#f1f5f9" if t["is_dark"] else "#0f172a",
        insertbackground="#38bdf8",
        selectbackground="#0284c7",
        selectforeground="#ffffff",
        padx=25,
        pady=20,
        relief="flat",
        highlightthickness=1,
        highlightbackground=t["border"]
    )
    scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=txt.yview, style="Vertical.TScrollbar")
    txt.configure(yscrollcommand=scrollbar.set)

    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    enable_smooth_mousewheel(txt)

    # Настройка типографики и тегов Markdown
    txt.tag_configure("h1", font=("Segoe UI", 16, "bold"), foreground="#38bdf8", spacing1=18, spacing3=8)
    txt.tag_configure("h2", font=("Segoe UI", 13, "bold"), foreground="#60a5fa", spacing1=16, spacing3=6)
    txt.tag_configure("h3", font=("Segoe UI", 11, "bold"), foreground="#93c5fd", spacing1=12, spacing3=4)
    txt.tag_configure("body", font=("Segoe UI", 10), foreground="#f1f5f9" if t["is_dark"] else "#1e293b", spacing1=2, spacing3=2)
    txt.tag_configure("bold", font=("Segoe UI", 10, "bold"), foreground="#ffffff" if t["is_dark"] else "#000000")
    txt.tag_configure("italic", font=("Segoe UI", 10, "italic"), foreground="#cbd5e1" if t["is_dark"] else "#475569")
    txt.tag_configure("bold_italic", font=("Segoe UI", 10, "bold italic"), foreground="#ffffff" if t["is_dark"] else "#000000")
    txt.tag_configure("code", font=("Consolas", 10), foreground="#38bdf8", background="#0d1b38" if t["is_dark"] else "#f1f5f9")
    txt.tag_configure("code_block", font=("Consolas", 9), foreground="#7dd3fc" if t["is_dark"] else "#0369a1", background="#070d1e" if t["is_dark"] else "#f8fafc", spacing1=1, spacing3=1, lmargin1=16, lmargin2=16)
    txt.tag_configure("table", font=("Consolas", 9), foreground="#7dd3fc" if t["is_dark"] else "#0369a1", background="#070d1e" if t["is_dark"] else "#f8fafc", lmargin1=16, lmargin2=16)
    txt.tag_configure("quote", font=("Segoe UI", 9, "italic"), foreground="#fbbf24", background="#1e293b" if t["is_dark"] else "#fef3c7", lmargin1=22, lmargin2=22, spacing1=3, spacing3=3)
    txt.tag_configure("alert_tip", font=("Segoe UI", 9), foreground="#38bdf8", background="#0c2340" if t["is_dark"] else "#ecfeff", lmargin1=22, lmargin2=22, spacing1=4, spacing3=4)
    txt.tag_configure("alert_note", font=("Segoe UI", 9), foreground="#93c5fd", background="#0f1f38" if t["is_dark"] else "#eff6ff", lmargin1=22, lmargin2=22, spacing1=4, spacing3=4)
    txt.tag_configure("alert_warn", font=("Segoe UI", 9), foreground="#fbbf24", background="#2a1b0a" if t["is_dark"] else "#fffbeb", lmargin1=22, lmargin2=22, spacing1=4, spacing3=4)
    txt.tag_configure("bullet", font=("Segoe UI", 10), foreground="#e2e8f0" if t["is_dark"] else "#334155", lmargin1=22, lmargin2=40, spacing1=2, spacing3=2)
    txt.tag_configure("bullet_dot", font=("Segoe UI", 10, "bold"), foreground="#38bdf8" if t["is_dark"] else "#0284c7")
    txt.tag_configure("num_list", font=("Segoe UI", 10), foreground="#e2e8f0" if t["is_dark"] else "#334155", lmargin1=22, lmargin2=42, spacing1=2, spacing3=2)
    txt.tag_configure("num_digit", font=("Segoe UI", 10, "bold"), foreground="#60a5fa" if t["is_dark"] else "#2563eb")
    txt.tag_configure("link", font=("Segoe UI", 10, "underline"), foreground="#38bdf8" if t["is_dark"] else "#0284c7")
    txt.tag_configure("hr", font=("Segoe UI", 8), foreground="#334155" if t["is_dark"] else "#cbd5e1", spacing1=8, spacing3=8)
    txt.tag_configure("heading_flash", background="#1e3a8a" if t["is_dark"] else "#bae6fd")
    txt.tag_configure("search_hit", background="#eab308", foreground="#000000")

    # Система гиперссылок и якорной навигации
    link_map = {}
    anchor_map = {}

    def norm_slug(s):
        if not s:
            return ""
        s = s.lower().replace('&', '').replace('#', '')
        return re.sub(r'[^a-z0-9а-яё]', '', s)

    def register_anchor(heading_text, pos):
        k1 = norm_slug(heading_text)
        if k1:
            anchor_map[k1] = pos
        m = re.search(r"(\d+)", heading_text)
        if m:
            anchor_map["num_" + m.group(1)] = pos
        text_only = re.sub(r"[\d\W]+", "", heading_text.lower())
        if text_only:
            anchor_map[text_only] = pos

    def handle_link_click(url):
        if url.startswith("#"):
            target_key = norm_slug(url)
            pos = anchor_map.get(target_key)
            if not pos:
                m = re.search(r"(\d+)", url)
                if m:
                    pos = anchor_map.get("num_" + m.group(1))
            if not pos:
                for ak, ap in anchor_map.items():
                    if (target_key and target_key in ak) or (ak and ak in target_key):
                        pos = ap
                        break
            if pos:
                try:
                    line_num = int(txt.index(pos).split('.')[0])
                    total_lines = max(1, int(txt.index(tk.END).split('.')[0]))
                    fraction = max(0.0, min(1.0, (line_num - 2) / total_lines))
                    txt.yview_moveto(fraction)
                    txt.tag_remove("heading_flash", "1.0", tk.END)
                    txt.tag_add("heading_flash", f"{line_num}.0", f"{line_num}.end")
                    dialog.after(1200, lambda: txt.tag_remove("heading_flash", "1.0", tk.END))
                except Exception:
                    txt.see(pos)
        elif url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:"):
            try:
                webbrowser.open(url)
            except Exception:
                pass

    def on_txt_motion(event):
        try:
            idx = txt.index(f"@{event.x},{event.y}")
            tags = txt.tag_names(idx)
            is_link = any(t in link_map or t == "link" for t in tags)
            txt.configure(cursor="hand2" if is_link else "")
        except Exception:
            pass

    def on_txt_click(event):
        try:
            idx = txt.index(f"@{event.x},{event.y}")
            tags = txt.tag_names(idx)
            for t in tags:
                if t in link_map:
                    handle_link_click(link_map[t])
                    return "break"
        except Exception:
            pass

    txt.bind("<Motion>", on_txt_motion)
    txt.bind("<Button-1>", on_txt_click)

    # Регулярное выражение для инлайн-разметки (ссылки, код, жирный, курсив)
    INLINE_PATTERN = re.compile(
        r'(?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^\)]+)\))|'
        r'(?P<code>`(?P<code_text>[^`]+)`)|'
        r'(?P<bold_italic>\*\*\*(?P<bi_text>[^\*]+)\*\*\*)|'
        r'(?P<bold>\*\*(?P<bold_text>[^\*]+)\*\*)|'
        r'(?P<italic>\*(?P<italic_text>[^\*]+)\*)'
    )

    def insert_formatted_inline(line_str, default_tag, extra_tags=None):
        extra = tuple(extra_tags) if extra_tags else ()
        last_idx = 0
        for m in INLINE_PATTERN.finditer(line_str):
            start, end = m.span()
            if start > last_idx:
                plain = line_str[last_idx:start]
                t_tags = (default_tag,) + extra if default_tag else extra
                txt.insert(tk.END, plain, t_tags)
            if m.group('link'):
                ltext = m.group('link_text')
                lurl = m.group('link_url')
                lid = f"link_{len(link_map)}"
                link_map[lid] = lurl
                t_tags = ("link", lid) + extra
                if default_tag:
                    t_tags = (default_tag,) + t_tags
                txt.insert(tk.END, ltext, t_tags)
            elif m.group('code'):
                ctext = m.group('code_text')
                t_tags = ("code",) + extra
                txt.insert(tk.END, ctext, t_tags)
            elif m.group('bold_italic'):
                bitext = m.group('bi_text')
                t_tags = ("bold_italic",) + extra
                if default_tag:
                    t_tags = (default_tag,) + t_tags
                txt.insert(tk.END, bitext, t_tags)
            elif m.group('bold'):
                btext = m.group('bold_text')
                t_tags = ("bold",) + extra
                if default_tag:
                    t_tags = (default_tag,) + t_tags
                txt.insert(tk.END, btext, t_tags)
            elif m.group('italic'):
                itext = m.group('italic_text')
                t_tags = ("italic",) + extra
                if default_tag:
                    t_tags = (default_tag,) + t_tags
                txt.insert(tk.END, itext, t_tags)
            last_idx = end
        if last_idx < len(line_str):
            plain = line_str[last_idx:]
            t_tags = (default_tag,) + extra if default_tag else extra
            txt.insert(tk.END, plain, t_tags)

    def format_table_block(table_lines):
        rows = []
        is_divider = []
        for l in table_lines:
            cells = [c.strip() for c in l.strip().strip('|').split('|')]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                is_divider.append(True)
                rows.append(cells)
            else:
                is_divider.append(False)
                clean_cells = [re.sub(r"[\*`]", "", c).strip() for c in cells]
                rows.append(clean_cells)

        if not rows:
            return

        num_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < num_cols:
                r.append("")

        col_w = []
        for c in range(num_cols):
            max_len = 4
            for i in range(len(rows)):
                if not is_divider[i] and c < len(rows[i]):
                    max_len = max(max_len, len(rows[i][c]))
            col_w.append(max_len)

        for i, r in enumerate(rows):
            if is_divider[i]:
                div_cells = ["-" * (col_w[c] + 2) for c in range(num_cols)]
                txt.insert(tk.END, "  |" + "+".join(div_cells) + "|\n", "table")
            else:
                cells_str = [f" {r[c].ljust(col_w[c])} " for c in range(num_cols)]
                txt.insert(tk.END, "  |" + "|".join(cells_str) + "|\n", "table")

    # Поиск и чтение FAQ.md
    base_dir = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", base_dir)
    candidates = [
        os.path.join(base_dir, "FAQ.md"),
        os.path.join(meipass, "FAQ.md"),
        os.path.join(os.getcwd(), "FAQ.md"),
        os.path.join(base_dir, "..", "FAQ.md"),
        os.path.join(os.path.dirname(base_dir), "FAQ.md"),
    ]
    faq_content = None
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    faq_content = f.read()
                break
            except Exception:
                pass

    if faq_content:
        lines = faq_content.splitlines()
        in_code = False
        idx = 0
        n_lines = len(lines)

        while idx < n_lines:
            raw_line = lines[idx]
            line = raw_line.strip()
            idx += 1

            # Блоки кода ``` ... ```
            if line.startswith("```"):
                in_code = not in_code
                continue

            if in_code:
                txt.insert(tk.END, raw_line + "\n", "code_block")
                continue

            # Пустая строка
            if not line:
                txt.insert(tk.END, "\n")
                continue

            # Таблицы (накапливаем смежные строки таблицы для ровного выравнивания)
            if line.startswith("|"):
                tbl_lines = [raw_line]
                while idx < n_lines and lines[idx].strip().startswith("|"):
                    tbl_lines.append(lines[idx])
                    idx += 1
                format_table_block(tbl_lines)
                txt.insert(tk.END, "\n")
                continue

            # Горизонтальный разделитель
            if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", line):
                txt.insert(tk.END, "─" * 68 + "\n\n", "hr")
                continue

            # Заголовки H1, H2, H3
            if line.startswith("# "):
                h_text = line[2:].strip()
                pos = txt.index("end-1c")
                register_anchor(h_text, pos)
                txt.insert(tk.END, h_text + "\n", "h1")
                continue
            elif line.startswith("## "):
                h_text = line[3:].strip()
                txt.insert(tk.END, "\n")
                pos = txt.index("end-1c")
                register_anchor(h_text, pos)
                txt.insert(tk.END, h_text + "\n", "h2")
                continue
            elif line.startswith("### "):
                h_text = line[4:].strip()
                txt.insert(tk.END, "\n")
                pos = txt.index("end-1c")
                register_anchor(h_text, pos)
                txt.insert(tk.END, h_text + "\n", "h3")
                continue

            # Цитаты и специальные блоки-уведомления (> [!TIP], > [!NOTE], и т.д.)
            if line.startswith(">"):
                q_text = line[1:].strip()
                alert_tag = "quote"
                prefix = ""
                if q_text.startswith("[!TIP]"):
                    alert_tag = "alert_tip"
                    prefix = "💡 СОВЕТ: "
                    q_text = q_text[6:].strip()
                elif q_text.startswith("[!NOTE]"):
                    alert_tag = "alert_note"
                    prefix = "ℹ️ ПРИМЕЧАНИЕ: "
                    q_text = q_text[7:].strip()
                elif q_text.startswith("[!WARNING]"):
                    alert_tag = "alert_warn"
                    prefix = "⚠️ ВНИМАНИЕ: "
                    q_text = q_text[10:].strip()
                elif q_text.startswith("[!IMPORTANT]"):
                    alert_tag = "alert_warn"
                    prefix = "❗ ВАЖНО: "
                    q_text = q_text[12:].strip()

                if prefix:
                    txt.insert(tk.END, "   " + prefix, (alert_tag, "bold"))
                    if q_text:
                        insert_formatted_inline(q_text, alert_tag)
                    txt.insert(tk.END, "\n")
                else:
                    txt.insert(tk.END, "   ", alert_tag)
                    insert_inline_target = q_text
                    insert_formatted_inline(insert_inline_target, alert_tag)
                    txt.insert(tk.END, "\n")
                continue

            # Нумерованный список (1. , 2. )
            num_m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", raw_line)
            if num_m:
                lead_spaces = len(num_m.group(1))
                num_str = num_m.group(2)
                rest = num_m.group(3)
                prefix_space = "    " if lead_spaces >= 2 else "  "
                txt.insert(tk.END, f"{prefix_space}{num_str}. ", ("num_list", "num_digit"))
                insert_formatted_inline(rest, "num_list")
                txt.insert(tk.END, "\n")
                continue

            # Маркированный список (- , * , • )
            bullet_m = re.match(r"^(\s*)([-*•])\s+(.*)$", raw_line)
            if bullet_m:
                lead_spaces = len(bullet_m.group(1))
                rest = bullet_m.group(3)
                if lead_spaces >= 2:
                    txt.insert(tk.END, "    ◦ ", ("bullet", "bullet_dot"))
                else:
                    txt.insert(tk.END, "  • ", ("bullet", "bullet_dot"))
                insert_formatted_inline(rest, "bullet")
                txt.insert(tk.END, "\n")
                continue

            # Обычный абзац текста
            insert_formatted_inline(raw_line, "body")
            txt.insert(tk.END, "\n")
    else:
        txt.insert(tk.END, "Руководство оператора и FAQ\n\nФайл FAQ.md не найден в каталоге программы.", "h1")

    txt.configure(state=tk.DISABLED)

    # Интерактивный поиск по тексту
    search_indices = []
    current_match_idx = [-1]

    def perform_search(event=None):
        txt.tag_remove("search_hit", "1.0", tk.END)
        query = search_entry.get().strip()
        search_indices.clear()
        current_match_idx[0] = -1

        if not query:
            match_lbl.configure(text="")
            return

        start_pos = "1.0"
        while True:
            pos = txt.search(query, start_pos, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end_pos = f"{pos}+{len(query)}c"
            txt.tag_add("search_hit", pos, end_pos)
            search_indices.append(pos)
            start_pos = end_pos

        count = len(search_indices)
        if count > 0:
            match_lbl.configure(text=f"Найдено: {count}")
            next_match()
        else:
            match_lbl.configure(text="Не найдено")

    def next_match(event=None):
        if not search_indices:
            return
        current_match_idx[0] = (current_match_idx[0] + 1) % len(search_indices)
        pos = search_indices[current_match_idx[0]]
        txt.see(pos)

    def clear_search():
        search_entry.delete(0, tk.END)
        txt.tag_remove("search_hit", "1.0", tk.END)
        search_indices.clear()
        current_match_idx[0] = -1
        match_lbl.configure(text="")

    search_entry.bind("<KeyRelease>", perform_search)
    search_entry.bind("<Return>", next_match)
    btn_clear_search.configure(command=clear_search)


# =============================================================================
# Диалог обратной связи
# =============================================================================
def show_feedback_dialog(parent, current_theme="dark"):
    t = THEMES[current_theme]
    dialog = tk.Toplevel(parent)
    dialog.title("✉️ Обратная связь и поддержка")
    dialog.geometry("520x420")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(bg=t["bg_app"])
    set_window_titlebar_theme(dialog, t["is_dark"])

    main_frame = tk.Frame(dialog, bg=t["bg_card"], padx=20, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

    tk.Label(main_frame, text="✉️ Обратная связь с разработчиком", font=("Segoe UI", 13, "bold"),
             bg=t["bg_card"], foreground=t["text_primary"]).pack(anchor="w", pady=(0, 10))

    info_text = (
        "Если у вас возникли вопросы, предложения по добавлению новых форматов компонентов, "
        "маркировок катушек или пожелания по улучшению алгоритмов объединения P&P и BOM — "
        "напишите автору проекта.\n\n"
        "• Автор: kean5782 (Анохин Александр Александрович)\n"
        "• Email: kean5782@yandex.ru\n"
        "• Создано совместно с нейросетью Gemini"
    )
    tk.Label(main_frame, text=info_text, justify=tk.LEFT, wraplength=460, font=("Segoe UI", 9),
             bg=t["bg_card"], foreground=t["text_secondary"]).pack(anchor="w", pady=(0, 15))

    btn_box = tk.Frame(main_frame, bg=t["bg_card"])
    btn_box.pack(fill=tk.X, pady=10)

    def open_email_client():
        subject = urllib.parse.quote("SMD Hub / BarcodeDecoder: Вопрос/Предложение")
        body = urllib.parse.quote("Здравствуйте, Александр!\n\n")
        webbrowser.open(f"mailto:kean5782@yandex.ru?subject={subject}&body={body}")

    def copy_email():
        parent.clipboard_clear()
        parent.clipboard_append("kean5782@yandex.ru")
        parent.update()
        messagebox.showinfo("Скопировано", "Email (kean5782@yandex.ru) скопирован в буфер обмена!", parent=dialog)

    btn_mail = tk.Button(btn_box, text="🚀 Открыть почтовую программу", command=open_email_client,
                         bg=t["accent"], fg=t["accent_text"], font=("Segoe UI", 9, "bold"),
                         relief="flat", padx=12, pady=6, cursor="hand2")
    btn_mail.pack(side=tk.LEFT, padx=(0, 10))

    btn_copy = tk.Button(btn_box, text="📋 Скопировать Email", command=copy_email,
                         bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], font=("Segoe UI", 9),
                         relief="flat", padx=12, pady=6, cursor="hand2")
    btn_copy.pack(side=tk.LEFT)

    tk.Button(main_frame, text="Закрыть", command=dialog.destroy,
              bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], font=("Segoe UI", 9),
              relief="flat", padx=15, pady=5, cursor="hand2").pack(anchor="e", pady=(15, 0))

