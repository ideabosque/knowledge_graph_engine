# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import csv
import io
from typing import Any, List, Optional


def parse_csv(file_content: str, delimiter: str = ",") -> List[dict]:
    """Parse CSV file content into list of dictionaries."""
    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    return list(reader)


def parse_excel(file_path: str, sheet_name: Optional[str] = None) -> List[dict]:
    """Parse Excel file into list of dictionaries."""
    import openpyxl

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb[sheet_name] if sheet_name else wb.active

    headers = [cell.value for cell in sheet[1]]
    rows = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        rows.append(dict(zip(headers, row)))

    return rows


def parse_file(file_path: str, file_type: Optional[str] = None) -> List[dict]:
    """
    Parse file based on type.
    Supported: csv, xlsx, xls
    """
    if not file_type:
        if file_path.endswith(".csv"):
            file_type = "csv"
        elif file_path.endswith((".xlsx", ".xls")):
            file_type = "excel"
        else:
            raise ValueError(f"Unsupported file type: {file_path}")

    if file_type == "csv":
        with open(file_path, "r") as f:
            return parse_csv(f.read())
    elif file_type == "excel":
        return parse_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")