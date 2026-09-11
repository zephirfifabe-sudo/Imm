import { z } from "zod";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { getHistory } from "@/lib/history/queries";
import { buildExportRows } from "@/lib/exports/rows";
import { rowsToCsv } from "@/lib/exports/csv";
import { rowsToXlsxBuffer } from "@/lib/exports/xlsx";

const querySchema = z.object({
  employeeId: z.string().uuid().optional(),
  siteId: z.string().uuid().optional(),
  from: z.string().min(1),
  to: z.string().min(1),
  format: z.enum(["csv", "xlsx"]).default("csv"),
});

/**
 * Export sécurisé: `requireCurrentUser()` exige une session valide (et
 * redirige vers /login sinon, comme pour n'importe quelle page) — jamais
 * de données d'une autre entreprise, l'entreprise vient de la session, pas
 * d'un paramètre de la requête.
 */
export async function GET(request: Request) {
  const { company } = await requireCurrentUser();

  const url = new URL(request.url);
  const parsed = querySchema.safeParse({
    employeeId: url.searchParams.get("employeeId") || undefined,
    siteId: url.searchParams.get("siteId") || undefined,
    from: url.searchParams.get("from") ?? "",
    to: url.searchParams.get("to") ?? "",
    format: url.searchParams.get("format") || undefined,
  });

  if (!parsed.success) {
    return Response.json({ error: "invalid_input" }, { status: 400 });
  }

  const from = new Date(parsed.data.from);
  const to = new Date(parsed.data.to);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
    return Response.json({ error: "invalid_input" }, { status: 400 });
  }

  const groups = await getHistory(company.id, {
    employeeId: parsed.data.employeeId,
    siteId: parsed.data.siteId,
    from,
    to,
  });
  const rows = buildExportRows(groups);

  const filenameBase = `klock-pointages_${parsed.data.from}_${parsed.data.to}`;

  if (parsed.data.format === "xlsx") {
    const buffer = await rowsToXlsxBuffer(rows);
    return new Response(new Uint8Array(buffer), {
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="${filenameBase}.xlsx"`,
      },
    });
  }

  const csv = rowsToCsv(rows);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filenameBase}.csv"`,
    },
  });
}
