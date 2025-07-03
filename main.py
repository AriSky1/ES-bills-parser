import os
import re
import csv
from datetime import datetime
from PyPDF2 import PdfReader

# Folder containing PDFs
pdf_folder = r"{folder to your ES bills}"
output_csv = "consumption_data.csv"
hours_output_csv = "hours_data.csv"

# Regex patterns
consumption_pattern = re.compile(
    r"Consommations (réelles|estimées) du (\d{2}/\d{2}/\d{4}) au (\d{2}/\d{2}/\d{4}) ?: ?([\d\s]+) kWh",
    re.IGNORECASE
)
total_pattern = re.compile(
    r"(Total à payer TTC|Total TTC en votre faveur)\s*:?[\s\n]*([\d\s,.]+)\s*€",
    re.IGNORECASE
)

hours_info = []

def parse_data_from_text(text):
    status = None
    from_date_str = None
    to_date_str = None
    kwh = None
    days_count = None
    total_value = None

    match = consumption_pattern.search(text)
    if match:
        status_raw, from_date_str, to_date_str, kwh_str = match.groups()
        status = "real" if status_raw.lower() == "réelles" else "estimation"
        try:
            from_date = datetime.strptime(from_date_str, "%d/%m/%Y")
            to_date = datetime.strptime(to_date_str, "%d/%m/%Y")
            days_count = (to_date - from_date).days
            kwh = int(kwh_str.replace(" ", ""))
        except Exception as e:
            print(f"Date/KWh parse error in text: {e}")

    total_match = total_pattern.search(text)
    if total_match:
        total_label, total_raw = total_match.groups()
        try:
            total_value = float(total_raw.replace(" ", "").replace(",", "."))
            if "en votre faveur" in total_label.lower():
                total_value = -total_value
        except Exception as e:
            print(f"Total parse error in text: {e}")

    return {
        "status": status,
        "from date": from_date_str,
        "to date": to_date_str,
        "kWh": kwh,
        "days count": days_count,
        "total": total_value
    }

def clean_number(num_str):
    return int(num_str.replace(" ", ""))

def extract_and_parse_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        hc_line = ""
        hp_line = ""
        taxes_value = ""
        tax_value = None
        without_tva_value = None
        subscription_value = None

        for line in text.splitlines():
            clean_line = line.strip()

            # Extract heures creuses and pleines
            if clean_line.lower().startswith("heures creuses"):
                hc_line = clean_line
            elif clean_line.lower().startswith("heures pleines"):
                hp_line = clean_line

            # Extract taxes line
            if clean_line.startswith("TAXES ET CONTRIBUTIONS"):
                taxes_value = clean_line
                match = re.search(r"(-?\d+,\d+)\s*€", clean_line)
                if match:
                    try:
                        tax_value = float(match.group(1).replace(",", "."))
                    except ValueError:
                        tax_value = None

            # Extract "MONTANT HORS TVA"
            if "MONTANT HORS TVA" in clean_line.upper():
                match = re.search(r"MONTANT HORS TVA.*?([\d\s,]+)\s*€?$", clean_line)
                if match:
                    try:
                        without_tva_value = float(match.group(1).replace(" ", "").replace(",", "."))
                    except ValueError:
                        without_tva_value = None

            # Extract "ABONNEMENT" subscription line
            if "ABONNEMENT" in clean_line.upper():
                match = re.search(r"ABONNEMENT.*?([\d\s,]+)\s*€?$", clean_line, re.IGNORECASE)
                if match:
                    try:
                        subscription_value = float(match.group(1).replace(" ", "").replace(",", "."))
                    except ValueError:
                        subscription_value = None

        file_basename = os.path.basename(pdf_path)

        if hc_line or hp_line:
            if hc_line:
                unit_price_match = re.search(r"0,\d{3,4}", hc_line)
                unit_price = unit_price_match.group(0) if unit_price_match else ""

                consumption_match = re.search(
                    r"(?:\(relevé \) 1|\(estimé \) 1|\d{2}/\d{2}/\d{4})\s+([\d ]+)(?=\s*0,)",
                    hc_line
                )
                consumption = clean_number(consumption_match.group(1)) if consumption_match else ""

                hours_info.append({
                    "name": file_basename,
                    "hours type": "Heures creuses",
                    "€/kWh": unit_price,
                    "consumption (kWh)": consumption,
                    "taxes (€)": taxes_value,
                    "tax (€)": tax_value,
                    "without TVA": without_tva_value,
                    "subscription": subscription_value
                })

            if hp_line:
                unit_price_match = re.search(r"0,\d{3,4}", hp_line)
                unit_price = unit_price_match.group(0) if unit_price_match else ""

                consumption_match = re.search(
                    r"(?:\(relevé \) 1|\(estimé \) 1|\d{2}/\d{2}/\d{4})\s+([\d ]+)(?=\s*0,)",
                    hp_line
                )
                consumption = clean_number(consumption_match.group(1)) if consumption_match else ""

                hours_info.append({
                    "name": file_basename,
                    "hours type": "Heures pleines",
                    "€/kWh": unit_price,
                    "consumption (kWh)": consumption,
                    "taxes (€)": taxes_value,
                    "tax (€)": tax_value,
                    "without TVA": without_tva_value,
                    "subscription": subscription_value
                })

        return parse_data_from_text(text)

    except Exception as e:
        print(f"Failed to read or parse {pdf_path}: {e}")
        return {
            "status": None,
            "from date": None,
            "to date": None,
            "kWh": None,
            "days count": None,
            "total": None
        }

# Write consumption CSV
with open(output_csv, mode="w", newline="", encoding="utf-8") as csvfile:
    fieldnames = ["filename", "status", "from date", "to date", "kWh", "days count", "total"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    for filename in os.listdir(pdf_folder):
        if filename.endswith(".pdf") and filename != "facture_26980081S.pdf":
            full_path = os.path.join(pdf_folder, filename)
            parsed_data = extract_and_parse_from_pdf(full_path)
            parsed_data["filename"] = filename
            writer.writerow(parsed_data)

# Write hours_data.csv
with open(hours_output_csv, mode="w", newline="", encoding="utf-8") as hours_file:
    fieldnames = ["name", "hours type", "€/kWh", "consumption (kWh)", "taxes (€)", "tax (€)", "without TVA", "subscription"]
    writer = csv.DictWriter(hours_file, fieldnames=fieldnames)
    writer.writeheader()
    for row in hours_info:
        writer.writerow(row)