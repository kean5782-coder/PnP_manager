#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BarcodeDecoder v1.1 — Десктопное приложение для декодирования маркировок и штрихкодов SMD компонентов.
Поддерживает конденсаторы (MLCC) и резисторы ведущих мировых и российских производителей.

Автоматически очищает префиксы и суффиксы катушек (1P, Q, 1T, суффиксы упаковок и партий)
и формирует унифицированное наименование компонента по стандарту:
  Резисторы:   R_<Размер>_<Номинал>_<Погрешность> (например, R_0603_10K_1%, R_0402_0R)
  Конденсаторы: C_<Размер>_<Диэлектрик>_<Емкость>_<Напряжение> (например, C_0603_X7R_100nF_50V)
"""

import os
import sys
import tkinter as tk
from tkinter import ttk
import re
import ctypes
import webbrowser
import urllib.parse
from datetime import datetime

try:
    import winreg
except ImportError:
    winreg = None

# Максимальное число удаляемых символов слева (префиксы катушек) и справа (суффиксы партий/упаковок)
MAX_TRIM_LEFT = 15
MAX_TRIM_RIGHT = 80


def format_g(num: float) -> str:
    """
    Форматирует число в компактную строку без научной нотации,
    с удалением незначащих нулей — аналог Kotlin DecimalFormat("0.######").
    Обеспечивает консистентность вывода между Python и Android версиями.
    """
    if num == 0:
        return '0'
    # До 6 знаков после запятой без научной нотации
    result = f"{num:.6f}"
    # Удаляем незначащие нули и лишнюю точку
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return result


# =============================================================================
# Парсинг российских обозначений резисторов (Р1-12, Р1-16)
# =============================================================================
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
    Выполняет регистронезависимый поиск ключа в словаре сопоставления.
    Поддерживает поиск в исходном, верхнем, нижнем регистре.
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
# Класс для хранения правила парсинга одного производителя
# =============================================================================
class VendorRule:
    """
    Правило парсинга кодировки компонентов конкретного производителя.
    
    Атрибуты:
        name (str): Имя производителя / серии (например, 'Murata', 'Yageo', 'Vishay').
        comp_type (str): Тип компонента ('resistor' или 'capacitor').
        pattern (re.Pattern): Скомпилированное регулярное выражение с именованными группами.
        size_map (dict): Таблица соответствия внутреннего кода типоразмера стандарту EIA (например, '10' -> '0603').
        dielectric_map (dict): Таблица соответствия кодов диэлектриков (для конденсаторов).
        voltage_map (dict): Таблица соответствия кодов рабочего напряжения.
        tolerance_map (dict): Таблица соответствия кодов погрешности/допуска (например, 'F' -> '1%').
        value_parser (callable): Пользовательская функция парсинга номинала (если требуется нестандартная логика).
        suffix_map (dict): Таблица соответствия суффиксов единиц измерения (например, 'R' -> 'Ω', 'L' -> 'mΩ').
        is_resistor (bool): Флаг резистора (True) или конденсатора (False).
    """

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
        """
        Проверяет строку кода на полное соответствие регулярному выражению правила.
        Возвращает словарь извлеченных именованных групп или None.
        """
        m = self.pattern.match(code)
        if m:
            return m.groupdict()
        return None


# =============================================================================
# Регулярное выражение для очистки стандартных префиксов катушек (EIA/CEA-863, EDIFACT, etc.)
# =============================================================================
BARCODE_PREFIX_REGEX = re.compile(
    r'^(?:ITEM\(1P\)|CUST\s*PROD\s*ID\(P\)|CUST\s*P/N|OUR\s*P/N|TDK\s*ITEM|P/N|ITEM|\(1P\)|\(30P\)|\(31P\)|\(1T\)|\(1S\)|\(6P\)|\(Q\)|\(V\)|\(P\)|1P|30P|31P|P|1T|1S|6P|9D|Q|V|K|D|10D|11D|12D)[:\s\-]*',
    re.IGNORECASE
)


# =============================================================================
# Парсер с автоматической очисткой префиксов и суффиксов
# =============================================================================
class VendorParser:
    """
    Движок сопоставления правил и очистки артефактов штрихкодов катушек.
    Выполняет токенизацию составных кодов (DataMatrix/QR), отсечение префиксов и перебор подстрок.
    """

    def __init__(self, rules):
        self.rules = rules

    def parse(self, code: str, vendor_name: str = None):
        """
        Парсит переданную строку кода со сканера или ручного ввода.
        
        Возвращает кортеж:
            (rule, groups, used_code, left_trim, right_trim)
            где rule — совпавшее правило (VendorRule),
                groups — словарь извлеченных параметров,
                used_code — подстрока кода, подошедшая под шаблон,
                left_trim, right_trim — число отсеченных символов слева и справа.
        """
        original = code.strip()
        if not original:
            return None, None, None, 0, 0

        # 1. Попытка разобрать строку целиком (как единичный токен)
        single_res = self._parse_single_token(original, vendor_name)
        if single_res[0] is not None:
            return single_res

        # 1.1 Попытка с удалением пробелов внутри (для этикеток, где часть артикула напечатана с пробелами, например "RC 0402 F R-07 33R2")
        if ' ' in original and not original.upper().startswith(('Р1-', 'P1-')):
            no_spaces = original.replace(' ', '')
            no_space_res = self._parse_single_token(no_spaces, vendor_name)
            if no_space_res[0] is not None:
                return no_space_res

        # 2. Если не подошло или строка содержит составные разделители (ISO 15434, CSV, &, /, etc.):
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
        Формирует стандартное унифицированное имя компонента на основе извлеченных параметров.
        Регистронезависимо сопоставляет все группы и параметры.
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

    # ---------- Парсинг значений резисторов (стандартный, для импортных) ----------
    def _parse_resistor_value(self, raw: str, suffix_map: dict) -> str:
        """
        Парсит строковое представление номинала резистора:
        - 3-значные и 4-значные коды EIA (103 -> 10K, 1002 -> 10K)
        - Буквенная нотация с точкой (10K0, 4K7, 1R00, 0R0)
        - Джамперы (0000, 000, 0) -> 0R
        """
        raw = raw.strip().upper()
        raw = re.sub(r'Ω', '', raw)
        raw = re.sub(r'(?i)ом', '', raw)

        if raw in ('0000', '000', '00', '0', '0R', '0R00', '0R0'):
            return '0R'

        # Обозначения с буквой внутри: 10K0, 4K70, 100R, 1R00, 1M00, 2M2
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

        # Суффиксы единиц (R, K, M, L) на конце
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

        # 3-значная цифровая кодировка (мантисса 2 цифры + множитель 10^N)
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
                    
        # 4-значная цифровая кодировка (мантисса 3 цифры + множитель 10^N)
        elif len(raw) == 4:
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

    # ---------- Парсинг значений конденсаторов ----------
    def _parse_capacitance_value(self, raw: str) -> str:
        """
        Парсит строковое представление емкости конденсатора:
        - 3-значный EIA код (104 -> 100nF, 101 -> 100pF, 106 -> 10uF)
        - Дробные значения с буквой R ( например, 4R7 -> 4.7pF, 0R5 -> 0.5pF)
        """
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
# Предустановленные правила для конденсаторов
# =============================================================================
def create_capacitor_rules():
    """Создает и возвращает список правил для конденсаторов мировых производителей."""
    rules = []

    # 1. CCTC (серия TCC)
    cctc_pattern = r'^TCC\s*(?P<size>\d{4})\s*(?P<dielectric>[A-Z0-9]+)\s*(?P<code>\d{3})\s*(?P<tolerance>[JKMZ])\s*(?P<voltage>\d{3})'
    cctc_size_map = {
        '0201': '0201', '0402': '0402', '0603': '0603',
        '0805': '0805', '1206': '1206', '1210': '1210'
    }
    cctc_dielectric = {
        'COG': 'C0G', 'X7R': 'X7R', 'X5R': 'X5R',
        'X6S': 'X6S', 'X7T': 'X7T', 'Y5V': 'Y5V'
    }
    cctc_voltage = {
        '500': '50V', '250': '25V', '160': '16V',
        '100': '10V', '6R3': '6.3V', '630': '63V'
    }
    cctc_tolerance = {
        'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'
    }
    rules.append(VendorRule('CCTC', 'capacitor', cctc_pattern, cctc_size_map,
                            dielectric_map=cctc_dielectric, voltage_map=cctc_voltage,
                            tolerance_map=cctc_tolerance, is_resistor=False))

    # 2. KEMET
    kemet_pattern = r'^C(?P<size>\d{4})(?P<type>[A-Z])(?P<code>\d{3})(?P<tolerance>[BCDFGJKMOPZ])(?P<voltage>\d)(?P<dielectric>[GRPUV])(?P<suffix>[A-Z]{0,4})$'
    kemet_size_map = {'0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210',
                      '1812': '1812', '1825': '1825', '2220': '2220', '2225': '2225'}
    kemet_dielectric = {'G': 'C0G', 'R': 'X7R', 'P': 'X5R', 'U': 'Z5U', 'V': 'Y5V'}
    kemet_voltage = {'1': '100V', '2': '200V', '3': '25V', '4': '16V', '5': '50V', '6': '35V', '7': '4V', '8': '10V', '9': '6.3V'}
    kemet_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.5pF', 'F': '1%', 'G': '2%', 'J': '5%',
        'K': '10%', 'M': '20%', 'Z': '+80%/-20%'
    }
    rules.append(VendorRule('KEMET', 'capacitor', kemet_pattern, kemet_size_map,
                            kemet_dielectric, kemet_voltage, kemet_tolerance, None, None, False))

    # 3. TAIYO YUDEN
    taiyo_pattern = r'^(?P<voltage>[PALJETGUHQSX])(?P<series>[MVW])(?P<termination>[KS])(?P<size>\d{3})(?P<size_tolerance>[A-E]?)(?P<dielectric>BJ|B7|C6|C7|LD|CG|UJ|UK)(?P<code>\d+R\d+|\d{3})(?P<tolerance>[ABCDFGJKMZ])(?P<thickness>[A-Z])(?P<special>[A-Z]?)-?(?P<packaging>[FTPRW]?)(?P<internal>[A-Z]?)$'
    taiyo_size_map = {
        '021': '008004', '042': '01005', '063': '0201', '105': '0402',
        '107': '0603', '212': '0805', '316': '1206', '325': '1210', '432': '1812'
    }
    taiyo_dielectric = {
        'BJ': 'X5R', 'B7': 'X7R', 'C6': 'X6S', 'C7': 'X7S',
        'LD': 'X5R', 'CG': 'C0G', 'UJ': 'U2J', 'UK': 'U2K'
    }
    taiyo_voltage = {
        'P': '2.5V', 'A': '4V', 'J': '6.3V', 'L': '10V', 'E': '16V',
        'T': '25V', 'G': '35V', 'U': '50V', 'H': '100V', 'Q': '250V',
        'S': '630V', 'X': '2000V'
    }
    rules.append(VendorRule('TaiyoYuden', 'capacitor', taiyo_pattern, taiyo_size_map,
                            dielectric_map=taiyo_dielectric, voltage_map=taiyo_voltage,
                            is_resistor=False))

    # 4. Murata (расширенный список диэлектриков и серий)
    dielectric_keys = [
        'X7R', 'X5R', 'X6S', 'X7S', 'X8R', 'Y5V', 'C0G', 'U2J',
        '5C', 'R7', 'R6', 'C7', 'R9',
        'C8', 'R8', 'X6T', 'X5S', 'X7T', 'X8L', 'X8G', 'X8P',
        'NP0', 'NPO'
    ]
    dielectric_pattern = '|'.join(dielectric_keys)
    murata_series = (
        'GRM|GJM|GQM|LLL|LLA|LLM|ERB|'
        'GCD|GCM|GCJ|GCH|GCE|GCQ|'
        'GMA|GNM|GR4|GR7|GA2|GA3|'
        'GC|GD|GF|GB'
    )
    murata_pattern = r'^(?P<series>' + murata_series + r')(?P<size>\d{2,3}[A-Z]?)(?P<dielectric>' + dielectric_pattern + r')(?P<voltage>[A-Z0-9]{2})(?P<code>\d{3})(?P<tolerance>[A-Z])(?P<rest>[A-Z0-9]*)$'
    murata_size_map = {
        '02': '01005', '03': '0201', '15': '0402', '18': '0603',
        '21': '0805', '31': '1206', '32': '1210', '43': '1812',
        '55': '2220',
        '022': '01005', '033': '0201', '155': '0402', '188': '0603',
        '216': '0805', '219': '0805', '316': '1206', '319': '1206',
        '329': '1210', '433': '1812', '555': '2220', '158': '0402',
        **{f'{code}{chr(c)}': size for code, size in [('15','0402'),('18','0603'),('21','0805'),('31','1206'),('32','1210'),('43','1812'),('55','2220')] for c in range(ord('A'), ord('Z')+1)}
    }
    murata_dielectric = {
        '5C': 'C0G', 'R7': 'X7R', 'R6': 'X5R', 'C7': 'X7S',
        'U2J': 'U2J', 'X7R': 'X7R', 'X5R': 'X5R', 'X6S': 'X6S',
        'X7S': 'X7S', 'X8R': 'X8R', 'Y5V': 'Y5V', 'C0G': 'C0G',
        'R9': 'X7R',
        'C8': 'X6S', 'R8': 'X8R', 'X6T': 'X6T', 'X5S': 'X5S',
        'X7T': 'X7T', 'X8L': 'X8L', 'X8G': 'X8G', 'X8P': 'X8P',
        'NP0': 'C0G', 'NPO': 'C0G'
    }
    murata_voltage = {
        '0G': '4V', '0J': '6.3V', '1A': '10V', '1C': '16V',
        '1E': '25V', '1H': '50V', '2A': '100V', '2D': '200V',
        '2E': '250V', '2H': '500V', '2J': '630V', '3A': '1kV',
        '3D': '2kV', '3F': '3.15kV', 'BB': '350V', 'E2': 'AC250V'
    }
    murata_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.5pF', 'F': '1%',
        'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '+80%/-20%'
    }
    rules.append(VendorRule('Murata', 'capacitor', murata_pattern, murata_size_map,
                            dielectric_map=murata_dielectric, voltage_map=murata_voltage,
                            tolerance_map=murata_tolerance, is_resistor=False))

    # 5. Samsung
    samsung_cap_pattern = r'^CL(?P<size>\d{2})(?P<dielectric>[ACBXYZF])(?P<code>\d{3}|[0-9]R[0-9])(?P<tolerance>[BCDFGJKMZ])(?P<voltage>[A-Z])(?P<rest>.*)$'
    samsung_size_map = {'02': '01005', '03': '0201', '05': '0402', '10': '0603', '21': '0805', '31': '1206', '32': '1210',
                        '42': '1808', '43': '1812', '55': '2220'}
    samsung_dielectric = {'C': 'C0G', 'A': 'X5R', 'B': 'X7R', 'X': 'X6S', 'F': 'Y5V', 'Y': 'X7S', 'Z': 'X7T'}
    samsung_voltage = {
        'R': '4V', 'Q': '6.3V', 'P': '10V', 'O': '16V', 'A': '25V', 'L': '35V', 'B': '50V', 'C': '100V',
        'D': '200V', 'E': '250V', 'F': '350V', 'G': '500V', 'H': '630V', 'I': '1000V', 'J': '2000V', 'K': '3000V'
    }
    samsung_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%',
        'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'
    }
    rules.append(VendorRule('Samsung_Cap', 'capacitor', samsung_cap_pattern, samsung_size_map,
                            samsung_dielectric, samsung_voltage, samsung_tolerance, None, None, False))

    # 6. TDK (включая автомобильную серию CGA)
    tdk_cap_pattern = r'^(?:C(?P<size>\d{4})|CGA(?P<cga_size>[2-8])[A-Z0-9]{1,2})(?P<dielectric>COG|C0G|X5R|X6S|X7R|X7S|X7T)(?P<voltage>0G|0J|1A|1C|1E|1V|1H|1N|2A|2E)(?P<code>\d{3})(?P<tolerance>[BCDFGJKM])(?P<rest>.*)$'
    tdk_size_map = {
        '0402': '01005', '0603': '0201', '1005': '0402', '1608': '0603', '2012': '0805', '3216': '1206',
        '3225': '1210', '4532': '1812', '5750': '2220',
        '2': '0402', '3': '0603', '4': '0805', '5': '1206', '6': '1210', '8': '1812'
    }
    tdk_dielectric = {'COG': 'C0G', 'C0G': 'C0G', 'X5R': 'X5R', 'X6S': 'X6S', 'X7R': 'X7R', 'X7S': 'X7S', 'X7T': 'X7T'}
    tdk_voltage = {'0G': '4V', '0J': '6.3V', '1A': '10V', '1C': '16V', '1E': '25V', '1V': '35V', '1H': '50V', '1N': '75V', '2A': '100V', '2E': '250V'}
    tdk_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%'
    }
    rules.append(VendorRule('TDK_Cap', 'capacitor', tdk_cap_pattern, tdk_size_map,
                            tdk_dielectric, tdk_voltage, tdk_tolerance, None, None, False))

    # 7. AVX / Kyocera AVX MLCC
    avx_cap_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|1812|2220)(?P<voltage>[ZY3512V7])(?P<dielectric>[ACDFG])(?P<code>\d{3}|[0-9]R[0-9])(?P<tolerance>[BCDFGJKMZ])(?P<pack>[A-Z0-9]{3,4})$'
    avx_size_map = {
        '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805',
        '1206': '1206', '1210': '1210', '1812': '1812', '2220': '2220'
    }
    avx_dielectric = {'A': 'C0G', 'C': 'X7R', 'D': 'X5R', 'F': 'X8R', 'G': 'Y5V'}
    avx_voltage = {
        'Z': '10V', 'Y': '16V', '3': '25V', '5': '50V',
        '1': '100V', '2': '200V', 'V': '250V', '7': '500V'
    }
    avx_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF', 'F': '1%', 'G': '2%',
        'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'
    }
    rules.append(VendorRule('AVX', 'capacitor', avx_cap_pattern, avx_size_map,
                            dielectric_map=avx_dielectric, voltage_map=avx_voltage,
                            tolerance_map=avx_tolerance, is_resistor=False))

    # 8. Walsin
    walsin_cap_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|1812)(?P<dielectric>[NBXSA])(?P<code>\d{3})(?P<tolerance>[ABCDFGJKMZ])(?P<voltage>\d{3})(?P<rest>.*)$'
    walsin_size_map = {'0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210', '1812': '1812'}
    walsin_dielectric = {'N': 'C0G', 'B': 'X7R', 'X': 'X5R', 'S': 'X6S', 'A': 'X7S'}
    walsin_voltage = {'040': '4V', '063': '6.3V', '100': '10V', '160': '16V', '250': '25V', '500': '50V'}
    walsin_tolerance = {
        'A': '0.05pF', 'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF',
        'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%', 'Z': '-20/+80%'
    }
    rules.append(VendorRule('Walsin_Cap', 'capacitor', walsin_cap_pattern, walsin_size_map,
                            walsin_dielectric, walsin_voltage, walsin_tolerance, None, None, False))

    # 9. Yageo (конденсаторы)
    yageo_cap_pattern = r'^(?P<prefix>CC|AC|C|CQ)(?P<size>\d{4})(?P<tolerance>[BCDFGJKM])(?P<packing>[A-Z]{0,2})(?P<dielectric>X5R|X7R|X6S|X7S|X8R|X8G|COG|C0G|NP0|NPO|Y5V)(?P<voltage>[A-Z0-9]?)(?P<rest>[A-Z]{0,2})(?P<code>\d{3}|[0-9]R[0-9]{1,2})$'
    yageo_size_map = {
        '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805',
        '1206': '1206', '1210': '1210', '1812': '1812', '2010': '2010', '2512': '2512'
    }
    yageo_dielectric = {
        'X5R': 'X5R', 'X7R': 'X7R', 'X6S': 'X6S', 'X7S': 'X7S',
        'X8R': 'X8R', 'X8G': 'X8G', 'COG': 'C0G', 'C0G': 'C0G',
        'NP0': 'C0G', 'NPO': 'C0G', 'Y5V': 'Y5V'
    }
    yageo_voltage = {
        '0': '100V', '4': '4V', '5': '6.3V', '6': '10V', '7': '16V',
        '8': '25V', '9': '50V', 'C': '100V', 'D': '200V', 'E': '250V',
        'F': '350V', 'G': '500V', 'H': '630V', 'I': '1000V', 'J': '2000V', 'K': '3000V'
    }
    yageo_tolerance = {
        'B': '0.10pF', 'C': '0.25pF', 'D': '0.50pF',
        'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'M': '20%'
    }
    rules.append(VendorRule('Yageo_Cap', 'capacitor', yageo_cap_pattern, yageo_size_map,
                            dielectric_map=yageo_dielectric, voltage_map=yageo_voltage,
                            tolerance_map=yageo_tolerance, is_resistor=False))

    return rules


# =============================================================================
# Предустановленные правила для резисторов (включая российские)
# =============================================================================
def create_resistor_rules():
    """Создает и возвращает список правил для резисторов мировых и российских производителей."""
    rules = []

    # 1. Vishay / Dale (серия CRCW)
    vishay_pattern = r'^CRCW(?P<size>0402|0603|0805|1206|1210|1218|2010|2512)(?P<code>\d{3,4}|\d+[RKM]\d*|0000)(?P<tolerance>[BDFJZN])(?P<tcr>[A-Z0-9]{1,2})(?P<pack>[A-Z]{2})$'
    vishay_size_map = {
        '0402': '0402', '0603': '0603', '0805': '0805', '1206': '1206',
        '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'
    }
    vishay_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%', 'Z': '0%', 'N': '0%'}
    rules.append(VendorRule('Vishay', 'resistor', vishay_pattern, vishay_size_map,
                            tolerance_map=vishay_tolerance, is_resistor=True))

    # 2. Panasonic (серия ERJ)
    panasonic_pattern = r'^ERJ-?(?P<size>1G|2G|2R|3G|3E|3R|6G|6E|6R|8G|8E|8R|14|12|1T)(?P<series>[A-Z]{0,2}?)(?:(?P<tolerance>[BDFGJKZ])|(?=[0-9R]))(?P<code>\d{3,4}|\d*R\d+|0R00)(?P<pack>[A-Z])$'
    panasonic_size_map = {
        '1G': '0201', '2G': '0402', '2R': '0402', '3G': '0603', '3E': '0603', '3R': '0603',
        '6G': '0805', '6E': '0805', '6R': '0805', '8G': '1206', '8E': '1206', '8R': '1206',
        '14': '1210', '12': '1812', '1T': '2512'
    }
    panasonic_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%', '0': '0%', '': '0%'}
    rules.append(VendorRule('Panasonic', 'resistor', panasonic_pattern, panasonic_size_map,
                            tolerance_map=panasonic_tolerance, is_resistor=True))

    # 3. Bourns (серии CR, CRA, CRB, CHP, CMP)
    bourns_pattern = r'^(?P<series>CR|CRA|CRB|CHP|CMP)(?P<size>01005|0201|0402|0603|0805|1206|1210|2010|2512)-?(?P<tolerance>[BDFGJ])(?P<tcr>[A-Z/]{1,3})-?(?P<code>\d{3,4}|\d*R\d+|000)(?P<pack>[A-Z0-9]*)$'
    bourns_size_map = {
        '01005': '01005', '0201': '0201', '0402': '0402', '0603': '0603',
        '0805': '0805', '1206': '1206', '1210': '1210', '2010': '2010', '2512': '2512'
    }
    bourns_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Bourns', 'resistor', bourns_pattern, bourns_size_map,
                            tolerance_map=bourns_tolerance, is_resistor=True))

    # 4. KOA Speer (серия RK73)
    koa_pattern = r'^RK73(?P<type>[A-Z])(?P<size>1F|1H|1E|1J|2A|2B|2E|W2H|W3A)(?P<pack>[A-Z]{2,4})(?P<code>\d{3,4}|\d*R\d+|000|0)?(?P<tolerance>[BDFGJKZ])?$'
    koa_size_map = {
        '1F': '01005', '1H': '0201', '1E': '0402', '1J': '0603',
        '2A': '0805', '2B': '1206', '2E': '1210', 'W2H': '2010', 'W3A': '2512'
    }
    koa_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%', '': '0%'}
    rules.append(VendorRule('KOA_Speer', 'resistor', koa_pattern, koa_size_map,
                            tolerance_map=koa_tolerance, is_resistor=True))

    # 5. Royal Ohm (серии WA, W8, WG, W4)
    royal_pattern = r'^(?P<size>0201|0402|0603|0805|1206|1210|2010|2512)(?P<power>[A-Z0-9]{2})(?P<tolerance>[BDFGJ])(?P<code>\d{3,4}|\d*R\d+|000)(?P<pack>[A-Z0-9]{3})$'
    royal_size_map = {
        '0201': '0201', '0402': '0402', '0603': '0603', '0805': '0805',
        '1206': '1206', '1210': '1210', '2010': '2010', '2512': '2512'
    }
    royal_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Royal_Ohm', 'resistor', royal_pattern, royal_size_map,
                            tolerance_map=royal_tolerance, is_resistor=True))

    # 6. ROHM MCR
    rohm_mcr_pattern = r'^MCR(?P<size>006|01|03|10|18|25|50|100)(?P<pack>[A-Z]{3,4})(?P<tolerance>[BDFGJ])(?P<tcr>[A-Z0-9]?)(?P<code>\d{3,4}|\d*R\d+|000)$'
    rohm_mcr_size_map = {
        '006': '0201', '01': '0402', '03': '0603', '10': '0805',
        '18': '1206', '25': '1210', '50': '2010', '100': '2512'
    }
    rohm_mcr_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('ROHM_MCR', 'resistor', rohm_mcr_pattern, rohm_mcr_size_map,
                            tolerance_map=rohm_mcr_tolerance, is_resistor=True))

    # 7. Viking (серия CR)
    viking_pattern = r'^CR-(?P<size>E5|01|02|03|05|06|10|0A|12|25|62)(?P<tolerance>[BDFJ])(?P<pack>[A-Z0-9]*?)-+(?P<value>[^\s]+)$'
    viking_size_map = {
        'E5': '01005', '01': '0201', '02': '0402', '03': '0603',
        '05': '0805', '06': '1206', '10': '1210', '0A': '2010',
        '12': '2512', '25': '1225', '62': '0612'
    }
    viking_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
    suffix_map_ohm = {'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ', 'L': 'mΩ'}
    rules.append(VendorRule('Viking', 'resistor', viking_pattern, viking_size_map,
                            tolerance_map=viking_tolerance, suffix_map=suffix_map_ohm, is_resistor=True))

    # 8. Yageo RC серия с поддержкой R в коде
    rc_pattern = r'^RC(?P<size>\d{4})(?P<tolerance>[BDFJ])(?P<code>[\dR]{3,5})(?P<pack>[A-Z]{0,2})$'
    rc_size_map = {
        '0075': '01005', '0100': '0201', '0201': '0201', '0402': '0402',
        '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210',
        '1218': '1218', '2010': '2010', '2512': '2512',
        '1005': '0402', '1608': '0603', '2012': '0805', '3216': '1206',
        '3225': '1210', '5025': '2010', '6432': '2512'
    }
    rc_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
    
    def rc_value_parser(raw: str) -> str:
        """Парсер номиналов для серий RC Yageo и RI HOTTECH."""
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
            
    rules.append(VendorRule('RC_Yageo', 'resistor', rc_pattern, rc_size_map,
                            tolerance_map=rc_tolerance, value_parser=rc_value_parser,
                            is_resistor=True))

    # 9. HOTTECH RI серия
    ri_pattern = r'^RI(?P<size>\d{4})L(?P<code>[\dR]{3,5})(?P<tolerance>[BDFJ])T$'
    ri_size_map = {
        '0075': '01005', '0100': '0201', '0201': '0201', '0402': '0402',
        '0603': '0603', '0805': '0805', '1206': '1206', '1210': '1210',
        '1218': '1218', '2010': '2010', '2512': '2512'
    }
    ri_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
    rules.append(VendorRule('RI_HOTTECH', 'resistor', ri_pattern, ri_size_map,
                            tolerance_map=ri_tolerance, value_parser=rc_value_parser,
                            is_resistor=True))

    # 10. ROHM ESR
    rohm_esr_pattern = r'^ESR(?P<size>01|03|10|18|25)(?P<pack>[A-Z]{3})(?P<tolerance>[DFJ])(?P<code>\d{3}|\d{4}|[0-9]R[0-9]{2})$'
    rohm_esr_size_map = {'01': '0402', '03': '0603', '10': '0805', '18': '1206', '25': '1210'}
    rohm_esr_tolerance = {'D': '0.5%', 'F': '1%', 'J': '5%'}
    rules.append(VendorRule('ROHM_ESR', 'resistor', rohm_esr_pattern, rohm_esr_size_map,
                            tolerance_map=rohm_esr_tolerance, suffix_map=suffix_map_ohm, is_resistor=True))

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
            
    rules.append(VendorRule('ROHM_PMR', 'resistor', rohm_pmr_pattern, rohm_pmr_size_map,
                            tolerance_map=rohm_pmr_tolerance, suffix_map={'L': 'mΩ'}, value_parser=pmr_value_parser, is_resistor=True))

    # 12. Samsung (резисторы)
    samsung_res_pattern = r'^(?P<prefix>RC|RCB|RF|RM|RN|RK|RP|RUT|RU|RUK|RJ|RCW|RCV|RCS|RFS|RPS|RH)(?P<size>\d{4})(?P<tolerance>[DFGJ])(?P<code>\d{3}|\d{4}|[0-9]R[0-9]{1,2})(?P<pack>[A-Z]{0,2})$'
    samsung_size_map_res = {'0402': '0402', '0603': '0603', '1005': '0402', '1608': '0603', '2012': '0805',
                            '3216': '1206', '3225': '1210', '5025': '2010', '6432': '2512'}
    samsung_tolerance_res = {'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%'}
    rules.append(VendorRule('Samsung_Res', 'resistor', samsung_res_pattern, samsung_size_map_res,
                            tolerance_map=samsung_tolerance_res, suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ'}, is_resistor=True))

    # 13. Walsin (резисторы)
    walsin_res_pattern = r'^(?P<prefix>WR|WW|WA|WT|WF|WK)(?P<size>\d{2})(?P<func>[A-Z]?)(?P<code>\d{3,4}|\d*R\d+)(?P<tolerance>[FJP]?)(?P<pack>[A-Z])(?P<term>[LGS])?$'
    walsin_size_map_res = {'01': '01005', '02': '0201', '04': '0402', '06': '0603', '08': '0805',
                           '10': '1210', '12': '1206', '18': '1218', '20': '2010', '25': '2512'}
    walsin_tolerance_res = {'F': '1%', 'J': '5%', '': '0%'}
    rules.append(VendorRule('Walsin_Res', 'resistor', walsin_res_pattern, walsin_size_map_res,
                            tolerance_map=walsin_tolerance_res, suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ', 'L': 'mΩ'}, is_resistor=True))

    # 14. Yageo (все серии резисторов)
    yageo_series = 'AC|RC|RT|RL|RV|RE|RA|RK|RS|RP|RQ|RN|RM|RJ'
    yageo_pattern = (
        r'^(?P<series>' + yageo_series + r')'
        r'(?P<size>\d{4})'
        r'(?P<tolerance>[A-Z])'
        r'(?P<pack>[A-Z]*)'
        r'-?(?P<reel>\d{2})?'
        r'(?P<value>\d+[RKM]\d*|\d{3,4}|0R00|0R0|0R|0000|000|00|0|\d+)L?$'
    )
    yageo_size_map = {
        '0075': '0075', '0100': '0100', '0201': '0201', '0402': '0402', '0603': '0603',
        '0805': '0805', '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'
    }
    yageo_tolerance = {'B': '0.1%', 'C': '0.25%', 'D': '0.5%', 'F': '1%', 'G': '2%', 'J': '5%', 'K': '10%', 'Z': '0%'}
    rules.append(VendorRule('Yageo', 'resistor', yageo_pattern, yageo_size_map,
                            tolerance_map=yageo_tolerance,
                            suffix_map={'R': 'Ω', 'K': 'KΩ', 'M': 'MΩ'},
                            is_resistor=True))

    # 15. Российские резисторы Р1-12 и Р1-16
    def make_tolerance_map():
        base = {
            "0.05": "0.05%", "0.1": "0.1%", "0.25": "0.25%",
            "0.5": "0.5%", "1": "1%", "2": "2%", "5": "5%",
            "10": "10%", "20": "20%"
        }
        result = {}
        for k, v in base.items():
            result[k] = v
            result[k.replace('.', ',')] = v
            result[v] = v
            result[v.replace('.', ',')] = v
        return result

    rus_tol_map = make_tolerance_map()

    # Р1-12
    rus_p1_12_pattern = r'^[РPрp]1-12[- ](?P<size>[\d.,]+)[- ]+(?P<value>.+?)[- ]+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_12_size_map = {
        "0.062": "0402", "0,062": "0402", "0.063": "0603", "0,063": "0603",
        "0.1": "0603", "0,1": "0603", "0.10": "0603", "0,10": "0603",
        "0.125": "0805", "0,125": "0805",
        "0.25": "1206", "0,25": "1206",
        "0.33": "1210", "0,33": "1210",
        "0.5": "2010", "0,5": "2010",
        "0.75": "2512", "0,75": "2512",
        "1.0": "2512", "1,0": "2512", "1": "2512",
        "2.0": "4020", "2,0": "4020", "2": "4020"
    }
    rules.append(VendorRule('Rus_P1-12', 'resistor', rus_p1_12_pattern, rus_p1_12_size_map,
                            tolerance_map=rus_tol_map,
                            value_parser=parse_russian_resistor_value,
                            is_resistor=True))

    # Р1-16
    rus_p1_16_pattern = r'^[РPрp]1-16[- ](?P<size>[\d.,]+)[- ]+(?P<value>.+?)[- ]+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_16_size_map = {
        "0.016": "0402", "0,016": "0402",
        "0.032": "0603", "0,032": "0603",
        "0.063": "0805", "0,063": "0805",
        "0.125": "1206", "0,125": "1206",
        "0.25": "2010", "0,25": "2010",
        "0.5": "2512", "0,5": "2512",
        "1.0": "4020", "1,0": "4020", "1": "4020"
    }
    rules.append(VendorRule('Rus_P1-16', 'resistor', rus_p1_16_pattern, rus_p1_16_size_map,
                            tolerance_map=rus_tol_map,
                            value_parser=parse_russian_resistor_value,
                            is_resistor=True))

    return rules


# =============================================================================
# Главное приложение – декодер по коду с автоматической очисткой
# =============================================================================
from smd_engine import (
    THEMES, set_window_titlebar_theme,
    show_faq_dialog, show_feedback_dialog, get_saved_theme, set_saved_theme
)

try:
    import smd_icons
    get_icon = smd_icons.get_icon
    apply_label_icon = smd_icons.apply_label_icon
    apply_button_icon = smd_icons.apply_button_icon
except Exception:
    def get_icon(*a, **k): return None
    def apply_label_icon(lbl, name, txt="", *a, **k): lbl.configure(text=txt)
    def apply_button_icon(btn, name, txt="", *a, **k):
        if txt: btn.configure(text=txt)


# =============================================================================
# Главное приложение – адаптивный современный интерфейс BarcodeDecoder
# =============================================================================
class BarcodeDecoderApp:
    """
    Адаптивный графический интерфейс для мгновенного декодирования SMD радиокомпонентов.
    Оптимизирован для любых мониторов (от ноутбуков до 2K/4K) и масштабов DPI.
    Выполнен по дизайн-системе SMD Hub (Dark Navy SaaS).
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BarcodeDecoder — Декодер SMD компонентов")

        # Установка иконки приложения (из файла или встроенного ресурса)
        self._setup_app_icon()

        # Расчет оптимального размера и центрирование окна на экране
        self._setup_window_geometry()

        # Инициализация движка правил
        rules = create_capacitor_rules() + create_resistor_rules()
        self.parser = VendorParser(rules)

        self.after_id = None
        self.toast_after_id = None
        self.active_theme_key = get_saved_theme()
        self.last_decoded_code = ""
        self.last_unified_name = ""

        # История текущей сессии
        self.history = []

        # Настройка ttk стилей
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Построение интерфейса
        self._build_ui()

        # Первичное применение темы
        self.apply_theme()

        # Фоновый мониторинг системного состояния (раскладка + системная тема)
        self.check_system_state_periodically()

    def _setup_app_icon(self):
        """Устанавливает иконку приложения в заголовок окна и на панель задач."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base_dir, "icon.ico"),
            os.path.join(getattr(sys, "_MEIPASS", base_dir), "icon.ico"),
            os.path.join(base_dir, "AndroidApp", "app", "src", "main", "res", "mipmap-xxxhdpi", "ic_launcher.png")
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    if path.endswith(".ico"):
                        self.root.iconbitmap(path)
                    else:
                        img = tk.PhotoImage(file=path)
                        self.root.iconphoto(True, img)
                    break
                except Exception:
                    pass

    def _setup_window_geometry(self):
        """Вычисляет пропорциональный размер окна в зависимости от разрешения экрана."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # Оптимальные размеры: ~1040x840 на 1080p/2K
        target_w = min(1040, max(920, int(screen_w * 0.65)))
        target_h = min(850, max(720, int(screen_h * 0.82)))

        pos_x = max(0, (screen_w - target_w) // 2)
        pos_y = max(10, (screen_h - target_h) // 2 - 25)

        self.root.geometry(f"{target_w}x{target_h}+{pos_x}+{pos_y}")
        self.root.minsize(860, 640)

    def _build_ui(self):
        """Создает и компонует все карточки и элементы интерфейса."""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Главный фоновый контейнер
        self.main_container = tk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # ---------------------------------------------------------------------
        # 1. ШАПКА ПРИЛОЖЕНИЯ (Header Card) — Фиксирована сверху
        # ---------------------------------------------------------------------
        self.header_card = tk.Frame(self.main_container, padx=20, pady=12)
        self.header_card.pack(fill=tk.X, padx=16, pady=(14, 8))
        self.header_card.columnconfigure(0, weight=1)
        self.header_card.columnconfigure(1, weight=0)

        # Левая колонка: Логотип и Название
        self.title_box = tk.Frame(self.header_card)
        self.title_box.grid(row=0, column=0, sticky="w")

        self.logo_label = tk.Label(self.title_box)
        apply_label_icon(self.logo_label, "lightning", text="", size=28)
        self.logo_label.pack(side=tk.LEFT, padx=(0, 12))

        self.text_box = tk.Frame(self.title_box)
        self.text_box.pack(side=tk.LEFT)

        self.title_label = tk.Label(self.text_box, text="BarcodeDecoder", font=("Segoe UI", 15, "bold"))
        self.title_label.pack(anchor="w")

        self.subtitle_label = tk.Label(
            self.text_box, text="Декодер маркировок SMD резисторов и конденсаторов (MLCC)", font=("Segoe UI", 9)
        )
        self.subtitle_label.pack(anchor="w")

        # Правая колонка: Раскладка и кнопки FAQ / Обратная связь
        self.controls_box = tk.Frame(self.header_card)
        self.controls_box.grid(row=0, column=1, sticky="e")

        # Компактный бейдж раскладки (фиксированный размер, не сдвигает кнопки)
        self.layout_badge = tk.Label(
            self.controls_box, text="🌐 EN", font=("Segoe UI", 9, "bold"),
            width=7, anchor="center", padx=6, pady=4
        )
        self.layout_badge.pack(side=tk.LEFT, padx=(0, 10))

        # Кнопка переключения темы (Вариант 1: безопасный запуск с сохранением)
        theme_btn_text = "☀️ Светлая" if self.active_theme_key == "dark" else "🌙 Тёмная"
        self.btn_theme = tk.Button(
            self.controls_box, text=f" {theme_btn_text}", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=5, cursor="hand2",
            command=self.toggle_theme
        )
        self.btn_theme.pack(side=tk.LEFT, padx=(0, 6))

        # Кнопки быстрого доступа: FAQ и Обратная связь (дизайн-система SMD Hub)
        self.btn_faq = tk.Button(
            self.controls_box, text=" FAQ / Справка", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: show_faq_dialog(self.root, self.active_theme_key)
        )
        apply_button_icon(self.btn_faq, "book", "FAQ / Справка", size=18)
        self.btn_faq.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_feedback = tk.Button(
            self.controls_box, text=" Обратная связь", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: show_feedback_dialog(self.root, self.active_theme_key)
        )
        apply_button_icon(self.btn_feedback, "mail", "Обратная связь", size=18)
        self.btn_feedback.pack(side=tk.LEFT)

        # ---------------------------------------------------------------------
        # Скроллируемая центральная область для адаптивности на любых экранах
        # ---------------------------------------------------------------------
        self.canvas_frame = tk.Frame(self.main_container)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=0)

        self.canvas = tk.Canvas(self.canvas_frame, bd=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview, style="Vertical.TScrollbar")
        self.content_frame = tk.Frame(self.canvas)

        self.content_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # self.scrollbar показывается динамически через _update_scrollbar_visibility

        # Автоматическая подгонка ширины содержимого под ширину окна
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.content_frame.bind("<Configure>", self._on_content_configure)

        # Привязка колеса мыши для плавной прокрутки по всему телу приложения
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", lambda e: self._on_mousewheel_btn(e, -2))
        self.root.bind_all("<Button-5>", lambda e: self._on_mousewheel_btn(e, 2))

        # ---------------------------------------------------------------------
        # 2. КАРТОЧКА ВВОДА (Input Card)
        # ---------------------------------------------------------------------
        self.input_card = tk.Frame(self.content_frame, padx=20, pady=14)
        self.input_card.pack(fill=tk.X, pady=(0, 8))

        self.input_header = tk.Frame(self.input_card)
        self.input_header.pack(fill=tk.X, pady=(0, 8))

        self.input_title = tk.Label(
            self.input_header, text="Введите код компонента (со сканера штрихкода или вручную):",
            font=("Segoe UI", 10, "bold")
        )
        self.input_title.pack(side=tk.LEFT)

        self.toast_label = tk.Label(self.input_header, text="", font=("Segoe UI", 9, "bold"))
        self.toast_label.pack(side=tk.RIGHT)

        # Строка поля ввода и кнопок действий
        self.entry_row = tk.Frame(self.input_card)
        self.entry_row.pack(fill=tk.X, pady=2)

        self.entry_frame = tk.Frame(self.entry_row, bd=1, relief=tk.SOLID)
        self.entry_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.entry = tk.Entry(
            self.entry_frame, font=("Consolas", 13), bd=0, relief=tk.FLAT
        )
        self.entry.pack(fill=tk.BOTH, expand=True, padx=10, pady=7)
        self.entry.focus_set()

        self.btn_decode = tk.Button(
            self.entry_row, text=" Расшифровать", font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, bd=0, padx=16, pady=7, cursor="hand2", command=self.on_decode
        )
        apply_button_icon(self.btn_decode, "lightning", "Расшифровать", size=18)
        self.btn_decode.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_paste = tk.Button(
            self.entry_row, text=" Вставить", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=7, cursor="hand2", command=self.on_paste_btn
        )
        apply_button_icon(self.btn_paste, "import", "Вставить", size=18)
        self.btn_paste.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_clear = tk.Button(
            self.entry_row, text=" Очистить", font=("Segoe UI", 9),
            relief=tk.FLAT, bd=0, padx=10, pady=7, cursor="hand2", command=self.clear_all
        )
        apply_button_icon(self.btn_clear, "trash", "Очистить", size=18)
        self.btn_clear.pack(side=tk.LEFT)

        # Привязка горячих клавиш
        self.entry.bind("<Return>", self.on_decode)
        self.entry.bind("<KeyRelease>", self.on_key_release)
        self.entry.bind("<<Paste>>", self.on_paste_event)
        self.entry.bind("<Control-v>", self.on_paste_event)
        self.entry.bind("<Control-V>", self.on_paste_event)
        self.entry.bind("<Control-KeyPress-v>", self.on_paste_event)
        self.entry.bind("<Control-KeyPress-V>", self.on_paste_event)
        self.entry.bind("<Shift-Insert>", self.on_paste_event)
        self.root.bind("<Escape>", self.clear_all)
        self.root.bind("<Control-l>", lambda e: self.entry.focus_set())
        self.root.bind("<Control-L>", lambda e: self.entry.focus_set())
        self.root.bind("<Control-v>", self.on_paste_event)
        self.root.bind("<Control-V>", self.on_paste_event)
        self.root.bind("<<Paste>>", self.on_paste_event)

        # ---------------------------------------------------------------------
        # 3. КАРТОЧКА РЕЗУЛЬТАТА (Result Card)
        # ---------------------------------------------------------------------
        self.result_card = tk.Frame(self.content_frame, padx=20, pady=14)
        self.result_card.pack(fill=tk.X, pady=(0, 8))

        self.result_header = tk.Frame(self.result_card)
        self.result_header.pack(fill=tk.X, pady=(0, 10))

        self.result_title = tk.Label(
            self.result_header, text="Результат декодирования", font=("Segoe UI", 11, "bold")
        )
        self.result_title.pack(side=tk.LEFT)

        # Бейджи типа и вендора (отображаются только при распознанном результате)
        self.badges_frame = tk.Frame(self.result_header)
        self.badges_frame.pack(side=tk.RIGHT)

        self.badge_type = tk.Label(
            self.badges_frame, text="", font=("Segoe UI", 9, "bold"), padx=10, pady=2
        )
        self.badge_vendor = tk.Label(
            self.badges_frame, text="", font=("Segoe UI", 9, "bold"), padx=10, pady=2
        )

        # Баннер унифицированного имени
        self.unified_banner = tk.Frame(self.result_card, padx=14, pady=10, bd=1, relief=tk.SOLID)
        self.unified_banner.pack(fill=tk.X, pady=(0, 10))

        self.unified_label = tk.Label(
            self.unified_banner, text="Ожидание ввода кода компонента...",
            font=("Consolas", 15, "bold"), anchor="w"
        )
        self.unified_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.banner_actions = tk.Frame(self.unified_banner)
        self.banner_actions.pack(side=tk.RIGHT)

        self.btn_copy = tk.Button(
            self.banner_actions, text=" Скопировать", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2", command=self.copy_unified_name
        )
        apply_button_icon(self.btn_copy, "export", "Скопировать", size=18)
        self.btn_copy.pack(side=tk.LEFT, padx=4)

        self.btn_search = tk.Button(
            self.banner_actions, text=" В браузере", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2", command=self.search_in_browser
        )
        apply_button_icon(self.btn_search, "rocket", "В браузере", size=18)
        self.btn_search.pack(side=tk.LEFT, padx=4)

        # Сетка ключевых параметров (4 плитки)
        self.params_grid = tk.Frame(self.result_card)
        self.params_grid.pack(fill=tk.X, pady=4)
        for i in range(4):
            self.params_grid.columnconfigure(i, weight=1, uniform="tile")

        self.tile_size = self._create_param_tile(self.params_grid, 0, "📐 Типоразмер (EIA)", "—")
        self.tile_value = self._create_param_tile(self.params_grid, 1, "⚡ Номинал", "—")
        self.tile_tolerance = self._create_param_tile(self.params_grid, 2, "🎯 Допуск / Диэлектрик", "—")
        self.tile_voltage = self._create_param_tile(self.params_grid, 3, "🔋 Напряжение", "—")

        # Блок очистки префиксов и технической информации
        self.details_box = tk.Frame(self.result_card, padx=12, pady=8, bd=1, relief=tk.SOLID)
        self.details_box.pack(fill=tk.X, pady=(10, 0))

        self.details_label = tk.Label(
            self.details_box, text="ℹ️ Для начала сканирования поднесите сканер к этикетке катушки или введите артикул.",
            font=("Segoe UI", 9), anchor="w", justify=tk.LEFT
        )
        self.details_label.pack(fill=tk.X)

        # ---------------------------------------------------------------------
        # 4. ИСТОРИЯ СЕССИИ (Session History Card)
        # ---------------------------------------------------------------------
        self.history_card = tk.Frame(self.content_frame, padx=20, pady=12)
        self.history_card.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.history_header = tk.Frame(self.history_card)
        self.history_header.pack(fill=tk.X, pady=(0, 6))

        self.history_title = tk.Label(
            self.history_header, text="История распознаваний в этой сессии (дважды кликните для копирования):",
            font=("Segoe UI", 9, "bold")
        )
        self.history_title.pack(side=tk.LEFT)

        self.btn_clear_history = tk.Button(
            self.history_header, text=" Очистить историю", font=("Segoe UI", 8),
            relief=tk.FLAT, bd=0, padx=8, pady=2, cursor="hand2", command=self.clear_history
        )
        apply_button_icon(self.btn_clear_history, "trash", "Очистить историю", size=16)
        self.btn_clear_history.pack(side=tk.RIGHT)

        self.tree_frame = tk.Frame(self.history_card)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("time", "raw_code", "comp_type", "vendor", "unified")
        self.history_tree = ttk.Treeview(
            self.tree_frame, columns=columns, show="headings", height=6, selectmode="browse"
        )
        self.history_tree.heading("time", text="Время")
        self.history_tree.heading("raw_code", text="Исходный код")
        self.history_tree.heading("comp_type", text="Тип")
        self.history_tree.heading("vendor", text="Производитель")
        self.history_tree.heading("unified", text="Унифицированное имя")

        self.history_tree.column("time", width=80, anchor="center", stretch=False)
        self.history_tree.column("raw_code", width=250, anchor="w", stretch=True)
        self.history_tree.column("comp_type", width=110, anchor="center", stretch=False)
        self.history_tree.column("vendor", width=120, anchor="center", stretch=False)
        self.history_tree.column("unified", width=240, anchor="w", stretch=True)

        tree_scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview, style="Vertical.TScrollbar")
        self.history_tree.configure(yscrollcommand=tree_scrollbar.set)

        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_tree.bind("<Double-1>", self.on_history_double_click)

        # ---------------------------------------------------------------------
        # 5. СТРОКА СОСТОЯНИЯ (Status Bar) — Фиксирована снизу
        # ---------------------------------------------------------------------
        self.status_bar = tk.Frame(self.main_container, padx=16, pady=5)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_icon = tk.Label(self.status_bar, bd=0)
        apply_label_icon(self.status_icon, "status_green", text="", size=16)
        self.status_icon.pack(side=tk.LEFT, padx=(0, 6))

        self.status_text = tk.Label(
            self.status_bar, text="Готов к работе", font=("Segoe UI", 9), anchor="w"
        )
        self.status_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_hint = tk.Label(
            self.status_bar, text="Enter: Расшифровать | Esc: Очистить | Ctrl+L: Фокус ввода | Двойной клик в истории: Скопировать",
            font=("Segoe UI", 8), anchor="e"
        )
        self.status_hint.pack(side=tk.RIGHT)

    def _create_param_tile(self, parent: tk.Widget, col: int, title: str, default_val: str) -> dict:
        """Создает карточку параметра в сетке."""
        tile = tk.Frame(parent, padx=10, pady=8, bd=1, relief=tk.SOLID)
        tile.grid(row=0, column=col, padx=4, pady=2, sticky="nsew")

        lbl_title = tk.Label(tile, text=title, font=("Segoe UI", 8), anchor="w")
        lbl_title.pack(fill=tk.X)

        lbl_val = tk.Label(tile, text=default_val, font=("Segoe UI", 12, "bold"), anchor="w")
        lbl_val.pack(fill=tk.X, pady=(2, 0))

        return {"frame": tile, "title": lbl_title, "value": lbl_val}

    def _on_canvas_configure(self, event):
        """Обновляет ширину содержимого при изменении размера окна."""
        self.canvas.itemconfig(self.content_window, width=event.width)
        self.root.after_idle(self._update_scrollbar_visibility)

    def _on_content_configure(self, event):
        """Обновляет область прокрутки canvas при изменении содержимого."""
        self.root.after_idle(self._update_scrollbar_visibility)

    def _update_scrollbar_visibility(self):
        """
        Динамически скрывает полосу прокрутки, если окно больше или равно содержимому,
        и показывает её только при нехватке места на экране.
        Предотвращает появление пустых полос сверху и снизу.
        """
        if not hasattr(self, "canvas") or not hasattr(self, "scrollbar") or not hasattr(self, "content_frame"):
            return

        try:
            bbox = self.canvas.bbox("all")
            content_h = (bbox[3] - bbox[1]) if bbox else self.content_frame.winfo_reqheight()
            canvas_h = self.canvas.winfo_height()

            if canvas_h <= 1:
                return

            if content_h > canvas_h + 4:
                # Содержимое больше окна: показываем скроллбар и задаем область прокрутки
                if not self.scrollbar.winfo_ismapped():
                    self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.canvas.configure(scrollregion=(0, 0, bbox[2] if bbox else self.canvas.winfo_width(), content_h))
            else:
                # Содержимое полностью помещается: скрываем скроллбар, фиксируем вид сверху без пустот
                if self.scrollbar.winfo_ismapped():
                    self.scrollbar.pack_forget()
                self.canvas.yview_moveto(0.0)
                self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), canvas_h))
        except Exception:
            pass

    def _on_mousewheel(self, event):
        """
        Универсальная плавная прокрутка колесиком мыши по всему телу приложения.
        Прокручивает окно только если его высота недостаточна для отображения всех элементов.
        """
        try:
            widget = event.widget
            # Проверяем, находится ли курсор над таблицей истории
            is_over_tree = False
            if hasattr(self, "history_tree"):
                if widget is self.history_tree or str(widget).startswith(str(self.history_tree)):
                    is_over_tree = True

            if is_over_tree and len(self.history_tree.get_children()) > 5:
                self.history_tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return "break"

            # Прокрутка основного холста только при реальной необходимости
            if hasattr(self, "canvas") and self.canvas.winfo_exists():
                bbox = self.canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                canvas_h = self.canvas.winfo_height()

                if content_h > canvas_h + 4:
                    delta = event.delta
                    if delta:
                        scroll_units = int(-1 * (delta / 120)) * 2
                        self.canvas.yview_scroll(scroll_units, "units")
                        return "break"
                else:
                    self.canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _on_mousewheel_btn(self, event, units: int):
        """Обработка кнопок прокрутки колеса мыши для Linux/X11."""
        try:
            widget = event.widget
            is_over_tree = False
            if hasattr(self, "history_tree"):
                if widget is self.history_tree or str(widget).startswith(str(self.history_tree)):
                    is_over_tree = True

            if is_over_tree and len(self.history_tree.get_children()) > 5:
                self.history_tree.yview_scroll(units, "units")
                return "break"

            if hasattr(self, "canvas") and self.canvas.winfo_exists():
                bbox = self.canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                canvas_h = self.canvas.winfo_height()

                if content_h > canvas_h + 4:
                    self.canvas.yview_scroll(units, "units")
                    return "break"
                else:
                    self.canvas.yview_moveto(0.0)
        except Exception:
            pass

    # =========================================================================
    # Стилизация интерфейса (Dark Navy SaaS Design System)
    # =========================================================================
    def _bind_hover(self, btn: tk.Button, bg_normal: str, bg_hover: str, fg_normal: str = None, fg_hover: str = None):
        """Плавное изменение фона кнопки при наведении курсора (SaaS Hover Effect)."""
        def on_enter(e):
            try:
                btn.configure(bg=bg_hover)
                if fg_hover:
                    btn.configure(fg=fg_hover)
            except Exception:
                pass
        def on_leave(e):
            try:
                btn.configure(bg=bg_normal)
                if fg_normal:
                    btn.configure(fg=fg_normal)
            except Exception:
                pass
        btn.bind("<Enter>", on_enter, add="+")
        btn.bind("<Leave>", on_leave, add="+")

    def apply_theme(self, theme_key: str = None):
        """Применяет цветовую палитру (Dark Navy или Tech Slate) ко всем элементам интерфейса."""
        if theme_key is not None:
            self.active_theme_key = theme_key
        c = THEMES[self.active_theme_key]

        # Настройка тёмного заголовка окна Windows 10/11
        set_window_titlebar_theme(self.root, c["is_dark"])

        # Базовый фон окна и холста
        self.root.configure(bg=c["bg_app"])
        self.main_container.configure(bg=c["bg_app"])
        self.canvas_frame.configure(bg=c["bg_app"])
        self.canvas.configure(bg=c["bg_app"])
        self.content_frame.configure(bg=c["bg_app"])

        # Шапка
        self.header_card.configure(bg=c["bg_card"])
        self.title_box.configure(bg=c["bg_card"])
        self.text_box.configure(bg=c["bg_card"])
        self.controls_box.configure(bg=c["bg_card"])

        self.logo_label.configure(bg=c["bg_card"])
        self.title_label.configure(bg=c["bg_card"], fg=c["text_primary"])
        self.subtitle_label.configure(bg=c["bg_card"], fg=c["text_muted"])

        # Кнопка темы, FAQ и Обратная связь
        theme_txt = "☀️ Светлая" if self.active_theme_key == "dark" else "🌙 Тёмная"
        self.btn_theme.configure(
            text=f" {theme_txt}",
            bg=c["btn_sec_bg"], fg=c["btn_sec_fg"],
            activebackground=c["btn_sec_hover"], activeforeground=c["text_primary"]
        )
        self._bind_hover(self.btn_theme, c["btn_sec_bg"], c["btn_sec_hover"])

        self.btn_faq.configure(
            bg=c["btn_sec_bg"], fg=c["btn_sec_fg"],
            activebackground=c["btn_sec_hover"], activeforeground=c["text_primary"]
        )
        self._bind_hover(self.btn_faq, c["btn_sec_bg"], c["btn_sec_hover"])

        self.btn_feedback.configure(
            bg=c["btn_sec_bg"], fg=c["btn_sec_fg"],
            activebackground=c["btn_sec_hover"], activeforeground=c["text_primary"]
        )
        self._bind_hover(self.btn_feedback, c["btn_sec_bg"], c["btn_sec_hover"])

        # Карточка ввода
        self.input_card.configure(bg=c["bg_card"])
        self.input_header.configure(bg=c["bg_card"])
        self.entry_row.configure(bg=c["bg_card"])
        self.input_title.configure(bg=c["bg_card"], fg=c["text_primary"])
        self.toast_label.configure(bg=c["bg_card"], fg=c["success_fg"])

        self.entry_frame.configure(bg=c["bg_input"], highlightbackground=c["border"], highlightcolor=c["border_focus"])
        self.entry.configure(bg=c["bg_input"], fg=c["text_primary"], insertbackground=c["text_primary"])

        self.btn_decode.configure(
            bg=c["accent"], fg=c["accent_text"],
            activebackground=c["accent_hover"], activeforeground=c["accent_text"]
        )
        self._bind_hover(self.btn_decode, c["accent"], c["accent_hover"])

        self.btn_paste.configure(
            bg=c["btn_sec_bg"], fg=c["btn_sec_fg"],
            activebackground=c["btn_sec_hover"], activeforeground=c["btn_sec_fg"]
        )
        self._bind_hover(self.btn_paste, c["btn_sec_bg"], c["btn_sec_hover"])

        self.btn_clear.configure(
            bg=c["btn_sec_bg"], fg=c["text_muted"],
            activebackground=c["btn_sec_hover"], activeforeground=c["text_primary"]
        )
        self._bind_hover(self.btn_clear, c["btn_sec_bg"], c["btn_sec_hover"])

        # Карточка результата
        self.result_card.configure(bg=c["bg_card"])
        self.result_header.configure(bg=c["bg_card"])
        self.badges_frame.configure(bg=c["bg_card"])
        self.result_title.configure(bg=c["bg_card"], fg=c["text_primary"])

        self.unified_banner.configure(bg=c["bg_card_inner"], highlightbackground=c["border"])
        self.unified_label.configure(bg=c["bg_card_inner"], fg=c["text_primary"] if self.last_unified_name else c["text_muted"])
        self.banner_actions.configure(bg=c["bg_card_inner"])

        self.btn_copy.configure(
            bg=c["accent"], fg=c["accent_text"],
            activebackground=c["accent_hover"], activeforeground=c["accent_text"]
        )
        self._bind_hover(self.btn_copy, c["accent"], c["accent_hover"])

        self.btn_search.configure(
            bg=c["btn_sec_bg"], fg=c["btn_sec_fg"],
            activebackground=c["btn_sec_hover"], activeforeground=c["btn_sec_fg"]
        )
        self._bind_hover(self.btn_search, c["btn_sec_bg"], c["btn_sec_hover"])

        self.params_grid.configure(bg=c["bg_card"])
        for tile in (self.tile_size, self.tile_value, self.tile_tolerance, self.tile_voltage):
            tile["frame"].configure(bg=c["bg_card_inner"], highlightbackground=c["border"])
            tile["title"].configure(bg=c["bg_card_inner"], fg=c["text_muted"])
            tile["value"].configure(bg=c["bg_card_inner"], fg=c["text_primary"] if self.last_unified_name else c["text_muted"])

        self.details_box.configure(bg=c["bg_card_inner"], highlightbackground=c["border"])
        self.details_label.configure(bg=c["bg_card_inner"], fg=c["text_secondary"])

        # История
        self.history_card.configure(bg=c["bg_card"])
        self.history_header.configure(bg=c["bg_card"])
        self.tree_frame.configure(bg=c["bg_card"])
        self.history_title.configure(bg=c["bg_card"], fg=c["text_secondary"])
        self.btn_clear_history.configure(
            bg=c["btn_sec_bg"], fg=c["text_muted"],
            activebackground=c["btn_sec_hover"], activeforeground=c["text_primary"]
        )
        self._bind_hover(self.btn_clear_history, c["btn_sec_bg"], c["btn_sec_hover"])

        # Стилизация Treeview под SaaS Dashboard
        self.style.configure(
            "Treeview",
            background=c["tree_bg"],
            foreground=c["tree_fg"],
            fieldbackground=c["tree_bg"],
            font=("Segoe UI", 9),
            rowheight=26
        )
        self.style.configure(
            "Treeview.Heading",
            background=c["tree_head_bg"],
            foreground=c["tree_head_fg"],
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "Treeview",
            background=[("selected", c["tree_sel_bg"])],
            foreground=[("selected", c["tree_sel_fg"])]
        )

        # Теги для чередования строк (зебра)
        self.history_tree.tag_configure("odd", background=c["row_odd"])
        self.history_tree.tag_configure("even", background=c["row_even"])

        # Стилизация полосы прокрутки под текущую тему
        self.style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background=c["scroll_thumb"],
            darkcolor=c["scroll_trough"],
            lightcolor=c["scroll_trough"],
            troughcolor=c["scroll_trough"],
            bordercolor=c["scroll_trough"],
            arrowcolor=c["scroll_arrow"],
            arrowsize=11
        )
        self.style.map(
            "Vertical.TScrollbar",
            background=[("active", c["scroll_thumb_hover"]), ("pressed", c["scroll_thumb_active"])],
            arrowcolor=[("active", c["text_primary"]), ("pressed", c["text_primary"])]
        )

        # Строка состояния
        self.status_bar.configure(bg=c["status_bg"])
        self.status_icon.configure(bg=c["status_bg"])
        self.status_text.configure(bg=c["status_bg"], fg=c["text_secondary"])
        self.status_hint.configure(bg=c["status_bg"], fg=c["text_muted"])

        # Обновление индикатора раскладки
        self.update_layout_status()

        # Динамическая проверка необходимости скроллбара
        self.root.after_idle(self._update_scrollbar_visibility)

    def toggle_theme(self):
        """Переключает тему оформления (dark <-> light), сохраняет настройку и мгновенно обновляет интерфейс."""
        new_theme = "light" if self.active_theme_key == "dark" else "dark"
        set_saved_theme(new_theme)
        self.apply_theme(new_theme)

    # =========================================================================
    # Проверка системного состояния (раскладка)
    # =========================================================================
    def is_russian_layout(self) -> bool:
        """Проверяет, установлена ли в текущий момент русская раскладка клавиатуры (для Windows)."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                thread_id = user32.GetWindowThreadProcessId(hwnd, 0)
                klid = user32.GetKeyboardLayout(thread_id)
            else:
                klid = user32.GetKeyboardLayout(0)
            lang_id = klid & 0xFFFF
            primary_lang = lang_id & 0x3FF
            return primary_lang == 0x19  # LANG_RUSSIAN = 0x19
        except Exception:
            return False

    def update_layout_status(self) -> bool:
        """Обновляет компактный индикатор раскладки клавиатуры и текст в строке состояния."""
        c = THEMES[self.active_theme_key]
        is_rus = self.is_russian_layout()

        if is_rus:
            self.layout_badge.configure(text="⚠️ RU", bg=c["warning_bg"], fg=c["warning_fg"])
            self.status_text.configure(
                text="⚠️ Внимание: включена русская раскладка клавиатуры. Для сканера рекомендуем переключить на английскую (EN).",
                fg=c["warning_fg"]
            )
            return True
        else:
            self.layout_badge.configure(text="🌐 EN", bg=c["success_bg"], fg=c["success_fg"])
            if self.status_text.cget("text").startswith("⚠️"):
                self.status_text.configure(text="Готов к работе", fg=c["text_secondary"])
            return False

    def check_system_state_periodically(self):
        """Фоновый таймер проверки раскладки клавиатуры."""
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self.update_layout_status()
        self.root.after(1000, self.check_system_state_periodically)

    # =========================================================================
    # Обработчики ввода и событий
    # =========================================================================
    def on_paste_btn(self):
        """Вставка из буфера обмена кнопкой с полной заменой текущего текста."""
        self.on_paste_event()

    def on_paste_event(self, event=None):
        """
        Событие вставки через горячие клавиши (Ctrl+V, Shift+Insert, <<Paste>>).
        Полностью очищает старый текст в поле ввода, вставляет новый из буфера и запускает декодирование.
        """
        try:
            clipboard_text = self.root.clipboard_get().strip()
            if clipboard_text:
                self.entry.delete(0, tk.END)
                self.entry.insert(0, clipboard_text)
                self.entry.focus_set()
                self.entry.icursor(tk.END)
                self.on_decode()
                return "break"
        except Exception:
            pass
        return "break"

    def on_key_release(self, event):
        """Автоматический запуск распознавания при наборе текста."""
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Return", "Escape"):
            return
        self.schedule_decode()

    def schedule_decode(self):
        """Дебаунс 350 мс перед запуском распознавания."""
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.after_id = self.root.after(350, self.auto_decode)

    def auto_decode(self):
        self.after_id = None
        self.on_decode()

    # =========================================================================
    # Основная логика декодирования
    # =========================================================================
    def on_decode(self, event=None):
        """Выполняет распознавание введенного штрихкода или артикула."""
        c = THEMES[self.active_theme_key]
        self.update_layout_status()

        code = self.entry.get().strip()
        if not code:
            self._reset_result_display()
            return

        self.status_text.configure(text="Идёт декодирование маркировки...", fg=c["accent"])

        rule, groups, used_code, left_trim, right_trim = self.parser.parse(code)

        if rule is None:
            self.last_decoded_code = code
            self.last_unified_name = ""
            self._render_not_found(code)
            return

        try:
            unified = self.parser.convert_to_unified(used_code, rule, groups)
        except Exception as e:
            self._render_error(f"Ошибка преобразования параметров: {e}")
            return

        self.last_decoded_code = code
        self.last_unified_name = unified

        # Отображение успешного результата
        self._render_success(rule, groups, used_code, left_trim, right_trim, unified)

        # Добавление в историю сессии
        self._add_to_history(code, rule.comp_type, rule.name, unified)

    def _render_success(self, rule: VendorRule, groups: dict, used_code: str, left_trim: int, right_trim: int, unified: str):
        """Отрисовывает успешно распознанный компонент."""
        c = THEMES[self.active_theme_key]

        # Заголовок и баннер
        self.unified_label.configure(text=unified, fg=c["text_primary"])
        self.btn_copy.configure(state=tk.NORMAL)
        self.btn_search.configure(state=tk.NORMAL)

        # Бейджи типа и производителя
        is_resistor = (rule.comp_type.lower() == "resistor")
        if is_resistor:
            self.badge_type.configure(text="🏷️ Резистор", bg=c["badge_res_bg"], fg=c["badge_res_fg"])
        else:
            self.badge_type.configure(text="🏷️ Конденсатор", bg=c["badge_cap_bg"], fg=c["badge_cap_fg"])
        self.badge_type.pack(side=tk.LEFT, padx=4)

        self.badge_vendor.configure(text=f"🏭 {rule.name}", bg=c["badge_vendor_bg"], fg=c["badge_vendor_fg"])
        self.badge_vendor.pack(side=tk.LEFT, padx=4)

        # Извлечение параметров для плиток
        size_val = groups.get("size") or groups.get("size_code") or groups.get("cga_size") or "—"
        size_display = map_lookup(rule.size_map, size_val, size_val)

        # Номинал
        val_display = groups.get("code") or groups.get("value") or groups.get("val") or "—"
        if rule.value_parser:
            try:
                val_display = rule.value_parser(val_display)
            except Exception:
                pass

        # Допуск / Диэлектрик
        tol_raw = groups.get("tolerance") or groups.get("cap_tolerance") or "—"
        tol_display = map_lookup(rule.tolerance_map, tol_raw, tol_raw)

        dielectric_raw = groups.get("dielectric") or groups.get("temp_code") or "—"
        dielectric_display = map_lookup(rule.dielectric_map, dielectric_raw, dielectric_raw)

        if is_resistor:
            tile3_title = "🎯 Погрешность"
            tile3_val = tol_display
        else:
            tile3_title = "🎯 Диэлектрик"
            tile3_val = dielectric_display

        # Напряжение
        volt_raw = groups.get("voltage") or "—"
        volt_display = map_lookup(rule.voltage_map, volt_raw, volt_raw if volt_raw != "—" else "—")

        # Обновление плиток параметров
        self.tile_size["title"].configure(text="📐 Типоразмер (EIA)")
        self.tile_size["value"].configure(text=size_display, fg=c["accent"])

        self.tile_value["title"].configure(text="⚡ Номинал")
        self.tile_value["value"].configure(text=val_display, fg=c["success_fg"])

        self.tile_tolerance["title"].configure(text=tile3_title)
        self.tile_tolerance["value"].configure(text=tile3_val, fg=c["text_primary"])

        self.tile_voltage["title"].configure(text="🔋 Напряжение" if not is_resistor else "📋 Допуск")
        self.tile_voltage["value"].configure(text=volt_display if not is_resistor else tol_display, fg=c["text_primary"])

        # Информационная строка очистки
        if left_trim > 0 or right_trim > 0:
            trims = []
            if left_trim > 0:
                trims.append(f"слева удалено {left_trim} симв.")
            if right_trim > 0:
                trims.append(f"справа удалено {right_trim} симв.")
            self.details_label.configure(
                text=f"✓ Распознано правило {rule.name} после очистки: '{used_code}' ({', '.join(trims)})",
                fg=c["success_fg"]
            )
        else:
            self.details_label.configure(
                text=f"✓ Распознано правило {rule.name} (код использован без изменений: '{used_code}')",
                fg=c["success_fg"]
            )

        self.status_text.configure(text=f"✓ Успешно распознано: {unified} ({rule.name})", fg=c["success_fg"])

    def _render_not_found(self, raw_code: str):
        """Отображает состояние, когда код не распознан."""
        c = THEMES[self.active_theme_key]

        self.unified_label.configure(text="❌ Код не распознан", fg=c["error_fg"])
        self.btn_copy.configure(state=tk.DISABLED)
        self.btn_search.configure(state=tk.NORMAL)

        # Скрываем бейджи
        self.badge_type.pack_forget()
        self.badge_vendor.pack_forget()

        for tile in (self.tile_size, self.tile_value, self.tile_tolerance, self.tile_voltage):
            tile["value"].configure(text="—", fg=c["text_muted"])

        hint_layout = " (Возможно, сканер ввёл русские буквы — переключите раскладку на EN)" if self.is_russian_layout() else ""
        self.details_label.configure(
            text=f"Код '{raw_code}' не совпал ни с одним правилом{hint_layout}. Нажмите 'В браузере' для поиска даташита.",
            fg=c["error_fg"]
        )
        self.status_text.configure(text=f"❌ Маркировка не распознана: {raw_code}{hint_layout}", fg=c["error_fg"])

    def _render_error(self, message: str):
        """Отображает сообщение об ошибке."""
        c = THEMES[self.active_theme_key]
        self.unified_label.configure(text=message, fg=c["warning_fg"])
        self.status_text.configure(text=message, fg=c["warning_fg"])

    def _reset_result_display(self):
        """Сбрасывает карточку результата в исходное состояние."""
        c = THEMES[self.active_theme_key]

        self.last_decoded_code = ""
        self.last_unified_name = ""

        self.unified_label.configure(text="Ожидание ввода кода компонента...", fg=c["text_muted"])
        self.btn_copy.configure(state=tk.DISABLED)
        self.btn_search.configure(state=tk.DISABLED)

        # Скрываем бейджи, чтобы не оставалось пустых плашек
        self.badge_type.pack_forget()
        self.badge_vendor.pack_forget()

        for tile in (self.tile_size, self.tile_value, self.tile_tolerance, self.tile_voltage):
            tile["value"].configure(text="—", fg=c["text_muted"])

        self.details_label.configure(
            text="ℹ️ Для начала сканирования поднесите сканер к этикетке катушки или введите артикул.",
            fg=c["text_secondary"]
        )
        self.status_text.configure(text="Готов к работе", fg=c["text_secondary"])

    def clear_all(self, event=None):
        """Очищает поле ввода и сбрасывает отображение."""
        self.entry.delete(0, tk.END)
        self._reset_result_display()
        self.update_layout_status()
        self.entry.focus_set()

    # =========================================================================
    # Вспомогательные действия (Копирование, Поиск, История)
    # =========================================================================
    def copy_unified_name(self):
        """Копирует унифицированное имя компонента в буфер обмена с тостом."""
        if not self.last_unified_name:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_unified_name)

        # Визуальный отклик (toast)
        self.toast_label.configure(text=f"✓ '{self.last_unified_name}' скопировано!")
        if self.toast_after_id is not None:
            self.root.after_cancel(self.toast_after_id)
        self.toast_after_id = self.root.after(2500, lambda: self.toast_label.configure(text=""))

    def search_in_browser(self):
        """Открывает поиск компонента в браузере по умолчанию (аналог Android-версии)."""
        code = self.last_decoded_code or self.entry.get().strip()
        if not code:
            return
        query = urllib.parse.quote(code)
        webbrowser.open(f"https://www.google.com/search?q={query}")

    def _add_to_history(self, raw_code: str, comp_type: str, vendor: str, unified: str):
        """Добавляет распознанный компонент в историю сессии."""
        now_str = datetime.now().strftime("%H:%M:%S")
        type_str = "Резистор" if comp_type.lower() == "resistor" else "Конденсатор"
        item = (now_str, raw_code, type_str, vendor, unified)
        self.history.insert(0, item)

        # Добавляем в Treeview в начало списка
        self.history_tree.insert("", 0, values=item)

        # Ограничиваем историю 50 записями
        children = self.history_tree.get_children()
        if len(children) > 50:
            self.history_tree.delete(children[-1])
            children = children[:-1]

        # Обновляем чередование цветов строк (SaaS Zebra Striping)
        for idx, item_id in enumerate(children):
            tag = "even" if idx % 2 == 0 else "odd"
            self.history_tree.item(item_id, tags=(tag,))

    def on_history_double_click(self, event):
        """Двойной клик по строке истории загружает код в поле ввода и копирует унифицированное имя."""
        selected = self.history_tree.selection()
        if not selected:
            return
        values = self.history_tree.item(selected[0], "values")
        if values and len(values) >= 5:
            raw_code = values[1]
            unified_name = values[4]
            self.entry.delete(0, tk.END)
            self.entry.insert(0, raw_code)
            self.last_unified_name = unified_name
            self.copy_unified_name()
            self.on_decode()

    def clear_history(self):
        """Очищает историю распознаваний сессии."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.history.clear()


# =============================================================================
# Точка входа
# =============================================================================
if __name__ == "__main__":
    # Включение High DPI Awareness на Windows для максимальной чёткости шрифтов
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    app = BarcodeDecoderApp(root)
    root.mainloop()


