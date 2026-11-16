"""Impor/ekspor CSV dan XLSX tanpa menjalankan formula Excel."""

import csv
import math
import os
import tempfile

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell

from statdesk.models.worksheet_model import (
    ColumnDefinition,
    WorksheetModel,
)


class DataIOError(Exception):
    """Kesalahan yang aman ditampilkan kepada pengguna."""


@dataclass
class ImportedDataset:
    columns: list[ColumnDefinition]
    rows: list[list]


class DataIOService:

    @staticmethod
    def sheet_names(path):
        try:
            wb = load_workbook(
                path,
                read_only=True,
                data_only=False
            )
            try:
                return list(wb.sheetnames)
            finally:
                wb.close()

        except (OSError, BadZipFile, ValueError, KeyError) as exc:
            raise DataIOError(
                f"Gagal membaca workbook: {exc}"
            ) from exc

    # =====================================
    # IMPORT EXCEL / CSV
    # =====================================

    @classmethod
    def import_file(
        cls,
        path,
        has_header=True,
        sheet_name=None
    ):
        path = Path(path)

        if path.suffix.lower() not in (".xlsx", ".csv"):
            raise DataIOError(
                "Hanya file .xlsx dan .csv yang didukung."
            )

        try:
            if path.suffix.lower() == ".csv":
                raw = cls._read_csv(path)
            else:
                raw = cls._read_xlsx(path, sheet_name)

            return cls._prepare(raw, has_header)

        except DataIOError:
            raise

        except (
            OSError, BadZipFile,
            UnicodeError, csv.Error,
            ValueError, KeyError
        ) as exc:
            raise DataIOError(
                f"Gagal mengimpor file: {exc}"
            ) from exc

    # =====================================
    # READ CSV
    # =====================================

    @staticmethod
    def _read_csv(path):
        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline=""
            ) as f:

                preview = f.read(8192)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(
                        preview,
                        delimiters=",;\t"
                    )
                    delimiter = dialect.delimiter

                except csv.Error:
                    delimiter = ","

                reader = csv.reader(
                    f,
                    delimiter=delimiter
                )

                rows = []

                for row in reader:
                    if not row:
                        continue

                    if len(row) > WorksheetModel.MAX_COLUMNS:
                        raise DataIOError(
                            "Jumlah kolom CSV melampaui batas 200."
                        )

                    rows.append(row)

                    if len(rows) > WorksheetModel.MAX_ROWS + 1:
                        raise DataIOError(
                            "Jumlah baris CSV melebihi "
                            "batas 50.000 data."
                        )

                return rows

        except UnicodeDecodeError as exc:
            raise DataIOError(
                "CSV harus berformat UTF-8. "
                "Buka di Excel dan simpan ulang "
                "sebagai 'CSV UTF-8' dahulu."
            ) from exc

    # =====================================
    # READ EXCEL
    # =====================================

    @staticmethod
    def _read_xlsx(path, sheet_name):

        wb = load_workbook(
            path,
            read_only=True,
            data_only=False
        )

        try:
            if not wb.worksheets:
                raise DataIOError(
                    "Workbook tidak memiliki worksheet."
                )

            if (
                sheet_name is not None
                and sheet_name not in wb.sheetnames
            ):
                raise DataIOError(
                    "Sheet tidak ditemukan pada workbook."
                )

            ws = (
                wb[sheet_name]
                if sheet_name
                else wb.worksheets[0]
            )

            if (
                ws.max_column
                and ws.max_column > WorksheetModel.MAX_COLUMNS
            ):
                raise DataIOError(
                    "Jumlah kolom Excel melampaui batas 200."
                )

            rows = []

            for excel_row in ws.iter_rows():
                converted = []

                for cell in excel_row:

                    if cell.data_type == "f":
                        raise DataIOError(
                            f"Ada formula di "
                            f"{ws.title}!{cell.coordinate}. "
                            "Salin hasilnya sebagai Values "
                            "di Excel sebelum impor."
                        )

                    if cell.data_type == "e":
                        raise DataIOError(
                            f"Ada nilai error Excel di "
                            f"{ws.title}!{cell.coordinate}."
                        )

                    value = cell.value

                    if isinstance(
                        value,
                        (date, datetime, time)
                    ):
                        value = value.isoformat()

                    elif isinstance(value, bool):
                        value = (
                            "TRUE" if value else "FALSE"
                        )

                    converted.append(value)

                rows.append(converted)

                if len(rows) > WorksheetModel.MAX_ROWS + 1:
                    raise DataIOError(
                        "Jumlah baris Excel melebihi "
                        "batas 50.000 data."
                    )

            return rows

        finally:
            wb.close()

    # =====================================
    # PREPARE DATASET
    # =====================================

    @classmethod
    def _prepare(cls, raw, has_header):

        if not raw:
            raise DataIOError(
                "File kosong; tidak ada data untuk diimpor."
            )

        width = max(map(len, raw))

        if (
            width < 1
            or width > WorksheetModel.MAX_COLUMNS
        ):
            raise DataIOError(
                "Jumlah kolom tidak valid (maksimal 200)."
            )

        headers = raw[0] if has_header else []

        body = raw[1:] if has_header else raw

        if len(body) > WorksheetModel.MAX_ROWS:
            raise DataIOError(
                "Dataset melampaui batas 50.000 baris."
            )

        names = []
        seen = set()

        for idx in range(width):

            initial = (
                str(headers[idx]).strip()
                if (
                    idx < len(headers)
                    and headers[idx] is not None
                )
                else ""
            )

            base = initial or f"Variable {idx + 1}"

            name = base
            count = 2

            while name.casefold() in seen:
                name = f"{base}_{count}"
                count += 1

            names.append(name)
            seen.add(name.casefold())

        padded = [
            list(r) + [None] * (width - len(r))
            for r in body
        ]

        columns = []

        for col in range(width):
            values = [
                r[col]
                for r in padded
                if (
                    r[col] is not None
                    and str(r[col]).strip()
                )
            ]

            numeric = (
                bool(values)
                and all(
                    cls._is_numeric(v)
                    for v in values
                )
            )

            columns.append(
                ColumnDefinition(
                    names[col],
                    "numeric" if numeric else "text"
                )
            )

        return ImportedDataset(
            columns,
            padded
        )

    # =====================================
    # DETECT NUMERIC
    # =====================================

    @staticmethod
    def _is_numeric(value):

        if isinstance(value, bool):
            return False

        if isinstance(value, str):
            stripped = value.strip()

            # ID seperti 00123 tetap Text
            if (
                stripped.lstrip("+-").isdigit()
                and len(stripped.lstrip("+-")) > 1
                and stripped.lstrip("+-").startswith("0")
            ):
                return False

        try:
            WorksheetModel._normalize(
                value,
                "numeric"
            )
            return True

        except (ValueError, TypeError):
            return False

    # =====================================
    # EXPORT EXCEL / CSV
    # =====================================

    @classmethod
    def export_file(cls, path, model):

        path = Path(path)
        suffix = path.suffix.lower()

        if suffix not in (".csv", ".xlsx"):
            raise DataIOError(
                "Pilih ekstensi .csv atau .xlsx."
            )

        columns, rows = model.export_snapshot()

        headers = [
            column.name
            for column in columns
        ]

        # Proteksi CSV Formula Injection
        if suffix == ".csv":

            for rownum, row in enumerate(
                [headers, *rows]
            ):
                for colnum, value in enumerate(row):

                    if (
                        isinstance(value, str)
                        and value.lstrip().startswith(
                            ("=", "+", "-", "@")
                        )
                    ):
                        raise DataIOError(
                            "CSV ditolak: teks di baris "
                            f"{rownum + 1}, kolom "
                            f"{colnum + 1} berpotensi "
                            "dianggap formula. "
                            "Ekspor sebagai XLSX agar teks "
                            "tersimpan apa adanya."
                        )

        # Menulis ke file sementara dahulu
        try:
            fd, tempname = tempfile.mkstemp(
                prefix="statdesk_",
                suffix=suffix,
                dir=path.parent
            )
            os.close(fd)

        except OSError as exc:
            raise DataIOError(
                "Tidak bisa membuat file di "
                f"folder tujuan: {exc}"
            ) from exc

        try:

            if suffix == ".csv":

                with open(
                    tempname,
                    "w",
                    encoding="utf-8-sig",
                    newline=""
                ) as file:

                    writer = csv.writer(file)
                    writer.writerow(headers)

                    writer.writerows([
                        [
                            "" if v is None else v
                            for v in row
                        ]
                        for row in rows
                    ])

            else:

                workbook = Workbook(write_only=True)

                sheet = workbook.create_sheet(
                    "Worksheet 1"
                )

                for row in [headers, *rows]:

                    cells = []

                    for value in row:

                        if isinstance(value, str):
                            cell = WriteOnlyCell(
                                sheet,
                                value=value
                            )

                            # Pastikan Text tidak
                            # berubah menjadi formula
                            cell.data_type = "s"

                            cells.append(cell)

                        else:
                            cells.append(value)

                    sheet.append(cells)

                workbook.save(tempname)

            # Ganti file tujuan hanya setelah
            # proses export selesai
            os.replace(tempname, path)

        except (
            OSError, ValueError, TypeError
        ) as exc:
            raise DataIOError(
                f"Gagal menyimpan file: {exc}"
            ) from exc

        finally:
            if os.path.exists(tempname):
                os.unlink(tempname)

        return len(rows)