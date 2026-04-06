from datetime import UTC, datetime

from googleapiclient.discovery import build


def fetch_contacts(sheet_id, creds):
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="A:D")
        .execute()
    )
    rows = result.get("values", [])
    if len(rows) < 2:
        return []
    header = [h.strip().lower() for h in rows[0]]
    contacts = []
    for row in rows[1:]:
        d = dict(zip(header, row + [""] * 4, strict=False))
        if (
            d.get("send", "").strip().lower() not in ("n", "no")
            and d.get("email", "").strip()
        ):
            contacts.append(
                {
                    "name": d.get("name", "").strip(),
                    "email": d["email"].strip(),
                }
            )
    return contacts


def get_already_sent(sheet_id, creds, slug):
    """Return set of emails already sent for this slug from the Sent Log tab."""
    service = build("sheets", "v4", credentials=creds)
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Sent Log!A:C")
            .execute()
        )
    except Exception:
        return set()
    rows = result.get("values", [])
    if len(rows) < 2:
        return set()
    return {
        row[0].strip().lower()
        for row in rows[1:]
        if len(row) >= 2 and row[1].strip() == slug
    }


def log_sent(sheet_id, creds, email, slug) -> None:
    """Append a row to the Sent Log tab."""
    service = build("sheets", "v4", credentials=creds)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    # Ensure the sheet tab exists
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tab_names = [s["properties"]["title"] for s in meta["sheets"]]
    if "Sent Log" not in tab_names:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": "Sent Log"}}}]},
        ).execute()
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sent Log!A1",
            valueInputOption="RAW",
            body={"values": [["email", "slug", "sent_at"]]},
        ).execute()
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sent Log!A:C",
        valueInputOption="RAW",
        body={"values": [[email, slug, timestamp]]},
    ).execute()
