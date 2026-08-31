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

import tkinter as tk
from tkinter import ttk, messagebox
import re
import ctypes

# Максимальное число удаляемых символов слева (префиксы катушек) и справа (суффиксы партий/упаковок)
MAX_TRIM_LEFT = 15
MAX_TRIM_RIGHT = 80


# =============================================================================
# Парсинг российских обозначений резисторов (Р1-12, Р1-16)
# =============================================================================
def parse_russian_resistor_value(raw: str) -> str:
    """
    Преобразует российское обозначение резистора (например, '1кОм', '4.7МОм', '100Ом', '10k', '4,7к')
    в международный формат с суффиксами R/K/M.
    Миллиомы (мОм) в текущей версии не поддерживаются.
    """
    raw = raw.lower().strip()
    raw = raw.replace('ом', '')
    raw = raw.replace('r', '')
    
    # Регулярное выражение с поддержкой как кириллических (к, м), так и латинских (k, m) букв
    match = re.match(r'^([\d.,]+)\s*([кkмm]?)', raw)
    if not match:
        return raw
        
    num_str = match.group(1).replace(',', '.')
    unit = match.group(2)
    
    try:
        num = float(num_str)
    except (ValueError, TypeError):
        return raw

    if unit in ('к', 'k'):
        return f"{num:.3g}K"
    elif unit in ('м', 'm'):
        return f"{num:.3g}M"
    else:
        # Автоматическое масштабирование Ом в К / М при больших числах
        if num >= 1000000:
            return f"{num / 1000000:.3g}M"
        elif num >= 1000:
            return f"{num / 1000:.3g}K"
        else:
            return f"{num:.3g}R"


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
# Парсер с автоматической очисткой префиксов и суффиксов
# =============================================================================
class VendorParser:
    """
    Движок сопоставления правил и очистки артефактов штрихкодов катушек.
    Выполняет перебор правил и перебор возможных подстрок (отсечение префиксов и суффиксов).
    """

    def __init__(self, rules):
        self.rules = rules

    def parse(self, code: str, vendor_name: str = None):
        """
        Парсит переданную строку кода.
        
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

        def try_match(candidate: str):
            candidate = candidate.strip()
            if not candidate:
                return None, None
            if vendor_name:
                for rule in self.rules:
                    if rule.name.lower() == vendor_name.lower():
                        groups = rule.match(candidate)
                        if groups:
                            return rule, groups
                return None, None
            else:
                for rule in self.rules:
                    groups = rule.match(candidate)
                    if groups:
                        return rule, groups
                return None, None

        # 1. Сначала пробуем сопоставить код целиком без удаления символов
        rule, groups = try_match(original)
        if rule is not None:
            return rule, groups, original, 0, 0

        # 2. Генерируем кандидатов обрезки префиксов и суффиксов
        candidates = []
        for left in range(0, MAX_TRIM_LEFT + 1):
            for right in range(0, MAX_TRIM_RIGHT + 1):
                if left == 0 and right == 0:
                    continue
                if left >= len(original) or right >= len(original):
                    continue
                candidates.append((left, right, left + right))

        # Сортируем кандидатов: сначала с наименьшим суммарным количеством удаленных символов
        candidates.sort(key=lambda x: (x[2], x[0]))

        for left, right, _ in candidates:
            if left + right >= len(original):
                continue
            candidate = original[left : len(original) - right]
            if not candidate:
                continue
            rule, groups = try_match(candidate)
            if rule is not None:
                return rule, groups, candidate, left, right

        return None, None, None, 0, 0

    def convert_to_unified(self, code: str, rule: VendorRule, groups: dict) -> str:
        """
        Формирует стандартное унифицированное имя компонента на основе извлеченных параметров.
        """
        if rule.is_resistor:
            size_code = groups.get('size') or groups.get('cga_size') or ''
            size = rule.size_map.get(size_code, size_code)
            raw_value = groups.get('value') or groups.get('code')
            if raw_value:
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_resistor_value(raw_value, rule.suffix_map)
            else:
                value_str = '0R' if groups.get('tolerance') in ('Z', '0') else '?'
            tolerance_code = groups.get('tolerance') or ''
            tolerance = rule.tolerance_map.get(tolerance_code, tolerance_code)
            
            if value_str == '0R' or tolerance == '0%':
                return f"R_{size}_0R"
            elif tolerance:
                return f"R_{size}_{value_str}_{tolerance}"
            else:
                return f"R_{size}_{value_str}"
        else:
            size_code = groups.get('size') or groups.get('cga_size') or ''
            size = rule.size_map.get(size_code, size_code)
            dielectric_code = groups.get('dielectric') or ''
            dielectric = rule.dielectric_map.get(dielectric_code, dielectric_code)
            raw_value = groups.get('code')
            if raw_value:
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_capacitance_value(raw_value)
            else:
                value_str = '?'
            voltage_code = groups.get('voltage')
            if voltage_code and voltage_code in rule.voltage_map:
                voltage = rule.voltage_map[voltage_code]
            else:
                voltage = '?'
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
                return f"{val:.3g}R"
            elif letter == 'K':
                return f"{val:.3g}K"
            elif letter == 'M':
                return f"{val:.3g}M"

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
                    return f"{val / 1000000:.3g}M"
                elif val >= 1000:
                    return f"{val / 1000:.3g}K"
                else:
                    return f"{val:.3g}R"
            elif unit == 'KΩ':
                return f"{val:.3g}K"
            elif unit == 'MΩ':
                return f"{val:.3g}M"
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
                return f"{val:.3g}R"
            elif raw.isdigit():
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val >= 1000000:
                    return f"{val / 1000000:.3g}M"
                elif val >= 1000:
                    return f"{val / 1000:.3g}K"
                else:
                    return f"{val:.3g}R"
                    
        # 4-значная цифровая кодировка (мантисса 3 цифры + множитель 10^N)
        elif len(raw) == 4:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except (ValueError, TypeError):
                    val = 0.0
                return f"{val:.3g}R"
            elif raw.isdigit():
                try:
                    mantissa = int(raw[:3])
                    multiplier = int(raw[3])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val >= 1000000:
                    return f"{val / 1000000:.3g}M"
                elif val >= 1000:
                    return f"{val / 1000:.3g}K"
                else:
                    return f"{val:.3g}R"
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
                return f"{val:.2g}pF"
            elif val < 1000:
                return f"{int(val)}pF" if val.is_integer() else f"{val:.2g}pF"
            elif val < 1000000:
                val_nf = val / 1000.0
                return f"{int(val_nf)}nF" if val_nf.is_integer() else f"{val_nf:.2g}nF"
            else:
                val_uf = val / 1000000.0
                return f"{int(val_uf)}uF" if val_uf.is_integer() else f"{val_uf:.2g}uF"
        else:
            if len(raw) == 3 and raw.isdigit():
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except (ValueError, TypeError):
                    return raw
                if val < 1000:
                    return f"{int(val)}pF" if val.is_integer() else f"{val:.2g}pF"
                elif val < 1000000:
                    val_nf = val / 1000.0
                    return f"{int(val_nf)}nF" if val_nf.is_integer() else f"{val_nf:.2g}nF"
                else:
                    val_uf = val / 1000000.0
                    return f"{int(val_uf)}uF" if val_uf.is_integer() else f"{val_uf:.2g}uF"
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
    kemet_pattern = r'^C(?P<size>\d{4})(?P<type>[A-Z])(?P<code>\d{3})(?P<tolerance>[BCDFGJKMOPZ])(?P<voltage>\d)(?P<dielectric>[GRPUV])(?P<suffix>[A-Z]{0,2})$'
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
        raw = raw.upper()
        if 'R' in raw:
            val_str = raw.replace('R', '.')
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                return raw
            if val >= 1000000:
                return f"{val / 1000000:.3g}M"
            elif val >= 1000:
                return f"{val / 1000:.3g}K"
            else:
                return f"{val:.3g}R"
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
        else:
            return raw
            
        if val >= 1000000:
            return f"{val / 1000000:.3g}M"
        elif val >= 1000:
            return f"{val / 1000:.3g}K"
        else:
            return f"{val:.3g}R"
            
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
            return f"{val_ohm:.3g}R"
        else:
            return raw
            
    rules.append(VendorRule('ROHM_PMR', 'resistor', rohm_pmr_pattern, rohm_pmr_size_map,
                            tolerance_map=rohm_pmr_tolerance, suffix_map={'L': 'mΩ'}, value_parser=pmr_value_parser, is_resistor=True))

    # 12. Samsung (резисторы)
    samsung_res_pattern = r'^(?P<prefix>RC|RCB|RF|RM|RN|RK|RP|RUT|RU|RUK|RJ|RCW|RCV|RCS|RFS|RPS|RH)(?P<size>\d{4})(?P<tolerance>[DFGJ])(?P<code>\d{3}|\d{4}|[0-9]R[0-9]{1,2})(?P<pack>[A-Z]{2})$'
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
    yageo_series = 'AC|RC|RT|RL|RV|RE|RA|RK|RS|RP|RQ|RN|RM'
    yageo_pattern = (
        r'^(?P<series>' + yageo_series + r')'
        r'(?P<size>\d{4})'
        r'(?P<tolerance>[BDFJ])'
        r'(?P<pack>[A-Z]*)'
        r'-?(?P<reel>\d{2})?'
        r'(?P<value>.+?)L$'
    )
    yageo_size_map = {
        '0075': '0075', '0100': '0100', '0201': '0201', '0402': '0402', '0603': '0603',
        '0805': '0805', '1206': '1206', '1210': '1210', '1218': '1218', '2010': '2010', '2512': '2512'
    }
    yageo_tolerance = {'B': '0.1%', 'D': '0.5%', 'F': '1%', 'J': '5%'}
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
    rus_p1_12_pattern = r'^Р1-12-(?P<size>[\d.,]+)\s+(?P<value>[^\s]+)\s+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_12_size_map = {
        "0.062": "0402", "0,062": "0402",
        "0.1": "0603", "0,1": "0603",
        "0.125": "0805", "0,125": "0805",
        "0.25": "1206", "0,25": "1206",
        "0.33": "1210", "0,33": "1210",
        "0.5": "2010", "0,5": "2010",
        "0.75": "2512", "0,75": "2512",
        "1.0": "2512", "1,0": "2512",
        "2.0": "4020", "2,0": "4020"
    }
    rules.append(VendorRule('Rus_P1-12', 'resistor', rus_p1_12_pattern, rus_p1_12_size_map,
                            tolerance_map=rus_tol_map,
                            value_parser=parse_russian_resistor_value,
                            is_resistor=True))

    # Р1-16
    rus_p1_16_pattern = r'^Р1-16-(?P<size>[\d.,]+)\s+(?P<value>[^\s]+)\s+(?P<tolerance>[\d.,]+)\s*%?.*$'
    rus_p1_16_size_map = {
        "0.016": "0402", "0,016": "0402",
        "0.032": "0603", "0,032": "0603",
        "0.063": "0805", "0,063": "0805",
        "0.125": "1206", "0,125": "1206",
        "0.25": "2010", "0,25": "2010",
        "0.5": "2512", "0,5": "2512",
        "1.0": "4020", "1,0": "4020"
    }
    rules.append(VendorRule('Rus_P1-16', 'resistor', rus_p1_16_pattern, rus_p1_16_size_map,
                            tolerance_map=rus_tol_map,
                            value_parser=parse_russian_resistor_value,
                            is_resistor=True))

    return rules


# =============================================================================
# Главное приложение – декодер по коду с автоматической очисткой
# =============================================================================
class BarcodeDecoderApp:
    """
    Графический интерфейс Tkinter для мгновенного декодирования кодов компонентов.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Расшифровка кода компонента v1.1")
        self.root.geometry("700x450")
        self.root.resizable(False, False)

        rules = create_capacitor_rules() + create_resistor_rules()
        self.parser = VendorParser(rules)

        self.after_id = None  # Идентификатор таймера для дебаунса ввода

        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Введите код компонента (со сканера или вручную):",
                  font=("Arial", 12)).pack(pady=(0, 10))

        self.entry = ttk.Entry(main_frame, font=("Arial", 14), width=40)
        self.entry.pack(pady=10)
        self.entry.focus_set()

        # Обработчики для копирования и выделения
        self.entry.bind('<Control-c>', self.copy_to_clipboard)
        self.entry.bind('<Control-C>', self.copy_to_clipboard)
        self.entry.bind('<Control-a>', self.select_all)
        self.entry.bind('<Control-A>', self.select_all)
        self.entry.bind('<Return>', self.on_decode)
        
        # Автоматическое распознавание при вводе
        self.entry.bind('<KeyRelease>', self.on_key_release)
        # Обработка вставки через буфер обмена
        self.entry.bind('<<Paste>>', self.on_paste_event)
        self.root.bind('<Escape>', self.clear_all)

        # Отслеживание фокуса и нажатий клавиш для моментального обновления статуса раскладки
        self.entry.bind('<FocusIn>', lambda e: self.update_layout_status())
        self.root.bind('<FocusIn>', lambda e: self.update_layout_status())
        self.entry.bind('<KeyPress>', lambda e: self.update_layout_status())

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Расшифровать", command=self.on_decode).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Очистить", command=self.clear_all).pack(side=tk.LEFT, padx=5)

        result_frame = ttk.LabelFrame(main_frame, text="Результат расшифровки", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.result_text = tk.Text(result_frame, height=8, font=("Courier New", 11), wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

        # Запуск регулярной проверки раскладки клавиатуры
        self.check_layout_periodically()

    # ---------- Проверка раскладки клавиатуры ----------
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
            return primary_lang == 0x19  # LANG_RUSSIAN = 0x19 (0x0419)
        except Exception:
            return False

    def update_layout_status(self) -> bool:
        """Обновляет строку состояния в зависимости от текущей раскладки клавиатуры."""
        is_rus = self.is_russian_layout()
        current_status = self.status_var.get()
        if is_rus:
            warning_msg = "⚠️ Для нормальной работы приложения смените раскладку на английскую."
            if current_status != warning_msg:
                self.status_var.set(warning_msg)
            return True
        else:
            if current_status.startswith("⚠️"):
                self.status_var.set("Готов к работе")
            return False

    def check_layout_periodically(self):
        """Периодически проверяет раскладку клавиатуры каждые 200 мс."""
        self.update_layout_status()
        self.root.after(200, self.check_layout_periodically)

    # ---------- Обработчики горячих клавиш ----------
    def copy_to_clipboard(self, event=None):
        try:
            selected = self.entry.selection_get()
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            return "break"
        except tk.TclError:
            pass

    def select_all(self, event=None):
        self.entry.select_range(0, tk.END)
        self.entry.icursor(tk.END)
        return "break"

    # ---------- Обработка вставки ----------
    def on_paste_event(self, event):
        """Событие вставки через буфер обмена."""
        self.root.after(10, self.after_paste)

    def after_paste(self):
        self.update_layout_status()
        self.schedule_decode()

    # ---------- Автоматическое распознавание ----------
    def on_key_release(self, event):
        self.update_layout_status()
        # Игнорируем нажатия клавиш-модификаторов
        if event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R'):
            return
        self.schedule_decode()

    def schedule_decode(self):
        """Дебаунс: запускает распознавание через 500 мс после последнего ввода."""
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.after_id = self.root.after(500, self.auto_decode)

    def auto_decode(self):
        self.after_id = None
        self.on_decode()

    # ---------- Основные методы ----------
    def on_decode(self, event=None):
        """Основной метод обработки и расшифровки введенного кода."""
        if self.is_russian_layout():
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "⚠️ Выбрана русская раскладка клавиатуры!\n")
            self.result_text.insert(tk.END, "Для корректной работы приложения переключите раскладку на английскую и введите код заново.\n")
            self.status_var.set("⚠️ Для нормальной работы приложения смените раскладку на английскую.")
            return

        code = self.entry.get().strip()
        if not code:
            self.result_text.delete(1.0, tk.END)
            if not self.status_var.get().startswith("⚠️"):
                self.status_var.set("Готов к работе")
            return

        self.status_var.set("Идёт распознавание...")
        self.result_text.delete(1.0, tk.END)

        rule, groups, used_code, left_trim, right_trim = self.parser.parse(code)
        if rule is None:
            self.result_text.insert(tk.END, "❌ Код не распознан ни одним правилом.\n")
            self.result_text.insert(tk.END, "Проверьте правильность ввода или добавьте новое правило.")
            self.status_var.set("Код не распознан")
            return

        try:
            unified = self.parser.convert_to_unified(used_code, rule, groups)
        except Exception as e:
            self.result_text.insert(tk.END, f"❌ Ошибка при преобразовании: {e}\n")
            self.status_var.set("Ошибка преобразования")
            return

        lines = [
            f"Производитель: {rule.name}",
            f"Тип компонента: {rule.comp_type}",
            "-" * 50,
            f"Унифицированное имя: {unified}",
            "-" * 50,
            "Извлечённые параметры:"
        ]
        for key, value in groups.items():
            lines.append(f"  {key}: {value}")
        lines.append("-" * 50)
        
        if left_trim > 0 or right_trim > 0:
            trim_parts = []
            if left_trim > 0:
                trim_parts.append(f"удалено {left_trim} символов слева")
            if right_trim > 0:
                trim_parts.append(f"удалено {right_trim} символов справа")
            lines.append(f"ℹ️  Распознан код после очистки: {used_code} ({', '.join(trim_parts)})")
        else:
            lines.append(f"ℹ️  Код использован без изменений: {used_code}")
            
        lines.append("✓ Расшифровка выполнена успешно.")

        self.result_text.insert(tk.END, "\n".join(lines))
        self.status_var.set(f"Распознано: {rule.name} ({rule.comp_type})")

    def clear_all(self, event=None):
        """Очищает поле ввода и окно результатов."""
        self.entry.delete(0, tk.END)
        self.result_text.delete(1.0, tk.END)
        self.status_var.set("Готов к работе")
        self.update_layout_status()
        self.entry.focus_set()


# =============================================================================
# Точка входа
# =============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = BarcodeDecoderApp(root)
    root.mainloop()
