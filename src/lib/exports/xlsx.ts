import "server-only";
import ExcelJS from "exceljs";
import { EXPORT_COLUMNS, type ExportRow } from "@/lib/exports/rows";

/**
 * Un vrai classeur .xlsx (pas un CSV renommé): évite les soucis
 * d'encodage/séparateur d'un CSV ouvert directement dans Excel, et permet
 * une mise en forme minimale (en-tête, largeurs de colonnes lisibles).
 */
export async function rowsToXlsxBuffer(rows: ExportRow[]): Promise<Buffer> {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Pointages");

  sheet.columns = EXPORT_COLUMNS.map((column) => ({
    header: column.header,
    key: column.key,
    width: Math.max(column.header.length + 2, 14),
  }));
  sheet.getRow(1).font = { bold: true };

  for (const row of rows) {
    sheet.addRow(row);
  }

  const arrayBuffer = await workbook.xlsx.writeBuffer();
  return Buffer.from(arrayBuffer);
}
