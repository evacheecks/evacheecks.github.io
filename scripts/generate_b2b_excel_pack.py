#!/usr/bin/env python3
"""
Generate the Eva Cheeks B2B Excel Asset Pack, the Unified CRM & Follow-up Tracker (.xlsx),
and the 9 Fiverr Gallery Images (1280x769 PNGs).
"""
import csv
import os
import subprocess
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = Path("/tmp")

# Colors
HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
SUBHEADER_FILL = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
ACCENT_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
GREEN_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
RED_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
BLUE_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="0F172A")
BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="0F172A")
BODY_FONT = Font(name="Calibri", size=10, bold=False, color="1E293B")

THIN_SIDE = Side(style="thin", color="CBD5E1")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)


def style_sheet_headers(ws, header_row=1):
    ws.views.sheetView[0].showGridLines = True
    ws.freeze_panes = f"A{header_row + 1}"
    for cell in ws[header_row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = CELL_BORDER
    ws.row_dimensions[header_row].height = 26


def auto_fit_columns(ws, min_width=12, max_width=42):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val = str(cell.value or "")
            if val.startswith("="):
                max_len = max(max_len, 14)
            else:
                max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 4, max_width))


def build_crm_workbook():
    wb = openpyxl.Workbook()
    # Tab 1: Outreach_CRM
    ws_crm = wb.active
    ws_crm.title = "Outreach_CRM"

    seed_csv = REPO_ROOT / "crm" / "outreach_crm_seed.csv"
    with seed_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    for r_idx, row in enumerate(rows, start=1):
        ws_crm.append(row)
        if r_idx > 1:
            status = row[8] if len(row) > 8 else ""
            row_fill = ZEBRA_FILL if r_idx % 2 == 0 else None
            if status in ("BOUNCED", "OPT_OUT", "SKIPPED_DUPLICATE"):
                row_fill = RED_FILL
            elif status == "FOLLOWUP_DUE":
                row_fill = ACCENT_FILL
            elif status == "QUALIFIED_READY":
                row_fill = GREEN_FILL
            elif status == "SENT_INITIAL":
                row_fill = BLUE_FILL

            for cell in ws_crm[r_idx]:
                cell.font = BODY_FONT
                cell.border = CELL_BORDER
                if row_fill:
                    cell.fill = row_fill

    style_sheet_headers(ws_crm, 1)
    auto_fit_columns(ws_crm)

    # Tab 2: Pending_Routes
    ws_routes = wb.create_sheet("Pending_Routes")
    routes_csv = TMP_DIR / "pending_routes.csv"
    if routes_csv.exists():
        with routes_csv.open("r", encoding="utf-8") as f:
            for row in csv.reader(f):
                ws_routes.append(row)
    else:
        ws_routes.append([
            "timestamp", "sender", "subject", "Classification", "Urgency",
            "Recommended_Action", "Draft_Reply", "Status", "Message_ID"
        ])
    for r_idx in range(2, ws_routes.max_row + 1):
        for cell in ws_routes[r_idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
    style_sheet_headers(ws_routes, 1)
    auto_fit_columns(ws_routes)

    # Tab 3: Send_Errors
    ws_err = wb.create_sheet("Send_Errors")
    err_csv = TMP_DIR / "send_errors.csv"
    if err_csv.exists():
        with err_csv.open("r", encoding="utf-8") as f:
            for row in csv.reader(f):
                ws_err.append(row)
    else:
        ws_err.append([
            "timestamp", "recipient_or_thread", "subject", "error_type",
            "details", "action_taken"
        ])
    for r_idx in range(2, ws_err.max_row + 1):
        for cell in ws_err[r_idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            cell.fill = RED_FILL
    style_sheet_headers(ws_err, 1)
    auto_fit_columns(ws_err)

    out_path = TMP_DIR / "Antigravity-CRM-and-Followup-Tracker.xlsx"
    wb.save(out_path)
    print(f"Saved {out_path}")
    return out_path


def build_b2b_1_restaurant_cogs():
    wb = openpyxl.Workbook()

    # Tab 1: 1_Ingredient_Master
    ws1 = wb.active
    ws1.title = "1_Ingredient_Master"
    ws1.append([
        "Ingredient_ID", "Ingredient_Name", "Category", "Supplier",
        "Purchase_Unit", "Pack_Cost", "Units_Per_Pack", "Yield_Pct",
        "Effective_Unit_Cost", "Notes"
    ])
    ingredients = [
        ("ING-001", "Espresso Beans (Single Origin)", "Coffee & Tea", "RoastCo Wholesale", "oz", 68.00, 80, 0.98, "=F2/(G2*H2)", "5 lb bag = 80 oz"),
        ("ING-002", "Whole Milk (Organic)", "Dairy & Alt", "Valley Dairy", "fl_oz", 22.40, 512, 0.99, "=F3/(G3*H3)", "4 gal case = 512 fl oz"),
        ("ING-003", "Barista Oat Milk", "Dairy & Alt", "OatCraft", "fl_oz", 34.50, 384, 0.99, "=F4/(G4*H4)", "12x32 oz case"),
        ("ING-004", "House Cardamom Brown Sugar Syrup", "Syrups", "In-House Batch", "fl_oz", 9.60, 64, 0.96, "=F5/(G5*H5)", "2 qt yield"),
        ("ING-005", "12oz Compostable Hot Cup + Lid", "Packaging", "EcoPack Supply", "each", 78.00, 500, 1.00, "=F6/(G6*H6)", "Sleeve of 500"),
        ("ING-006", "Sourdough Country Loaf", "Bakery", "Hearth Bakehouse", "slice", 6.50, 14, 0.95, "=F7/(G7*H7)", "14 usable slices/loaf"),
        ("ING-007", "Hass Avocados (#48 Count)", "Produce", "FreshDirect Local", "each", 54.00, 48, 0.78, "=F8/(G8*H8)", "After pit/skin trim"),
        ("ING-008", "Pasture-Raised Eggs", "Dairy & Alt", "Sunny Ridge Farm", "each", 63.00, 180, 0.97, "=F9/(G9*H9)", "15 dozen flat"),
        ("ING-009", "Saffron Threads (Spanish Coupe)", "Spices", "Silk Road Imports", "gram", 84.00, 28, 0.99, "=F10/(G10*H10)", "1 oz tin = 28g"),
        ("ING-010", "Wild Gulf Shrimp (16/20 Peeled)", "Seafood & Meat", "Harbor Seafood", "oz", 118.00, 160, 0.92, "=F11/(G11*H11)", "10 lb box = 160 oz"),
    ]
    for idx, row in enumerate(ingredients, start=2):
        ws1.append(list(row))
        ws1[f"F{idx}"].number_format = "$#,##0.00"
        ws1[f"H{idx}"].number_format = "0.0%"
        ws1[f"I{idx}"].number_format = "$#,##0.000"
        for cell in ws1[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws1, 1)
    auto_fit_columns(ws1)

    # Tab 2: 2_Recipe_COGS_Calculator
    ws2 = wb.create_sheet("2_Recipe_COGS_Calculator")
    ws2.append([
        "Menu_Item", "Ingredient_ID", "Ingredient_Name", "Unit_Measure",
        "Qty_Used", "Effective_Unit_Cost", "Line_Cost", "Recipe_Batch_Notes"
    ])
    recipe_lines = [
        ("Cardamom Brown Sugar Latte (12oz)", "ING-001", "Espresso Beans (Single Origin)", "oz", 0.75, "='1_Ingredient_Master'!I2", "=E2*F2", "Double shot (21g)"),
        ("Cardamom Brown Sugar Latte (12oz)", "ING-002", "Whole Milk (Organic)", "fl_oz", 9.00, "='1_Ingredient_Master'!I3", "=E3*F3", "Steamed milk"),
        ("Cardamom Brown Sugar Latte (12oz)", "ING-004", "House Cardamom Brown Sugar Syrup", "fl_oz", 1.25, "='1_Ingredient_Master'!I5", "=E4*F4", "House signature syrup"),
        ("Cardamom Brown Sugar Latte (12oz)", "ING-005", "12oz Compostable Hot Cup + Lid", "each", 1.00, "='1_Ingredient_Master'!I6", "=E5*F5", "Cup + lid + sleeve"),
        ("Oat Milk Cortado (8oz)", "ING-001", "Espresso Beans (Single Origin)", "oz", 0.75, "='1_Ingredient_Master'!I2", "=E6*F6", "Double shot"),
        ("Oat Milk Cortado (8oz)", "ING-003", "Barista Oat Milk", "fl_oz", 4.50, "='1_Ingredient_Master'!I4", "=E7*F7", "Textured oat milk"),
        ("Oat Milk Cortado (8oz)", "ING-005", "12oz Compostable Hot Cup + Lid", "each", 1.00, "='1_Ingredient_Master'!I6", "=E8*F8", "Cup + lid"),
        ("Sourdough Avocado & Poached Egg Toast", "ING-006", "Sourdough Country Loaf", "slice", 2.00, "='1_Ingredient_Master'!I7", "=E9*F9", "Thick country slices"),
        ("Sourdough Avocado & Poached Egg Toast", "ING-007", "Hass Avocados (#48 Count)", "each", 1.00, "='1_Ingredient_Master'!I8", "=E10*F10", "Whole smashed avocado"),
        ("Sourdough Avocado & Poached Egg Toast", "ING-008", "Pasture-Raised Eggs", "each", 2.00, "='1_Ingredient_Master'!I9", "=E11*F11", "Two poached eggs"),
        ("Saffron Garlic Gulf Shrimp Skillet", "ING-010", "Wild Gulf Shrimp (16/20 Peeled)", "oz", 6.50, "='1_Ingredient_Master'!I11", "=E12*F12", "6.5 oz portion"),
        ("Saffron Garlic Gulf Shrimp Skillet", "ING-009", "Saffron Threads (Spanish Coupe)", "gram", 0.25, "='1_Ingredient_Master'!I10", "=E13*F13", "Infused saffron oil"),
        ("Saffron Garlic Gulf Shrimp Skillet", "ING-006", "Sourdough Country Loaf", "slice", 2.00, "='1_Ingredient_Master'!I7", "=E14*F14", "Grilled bread side"),
    ]
    for idx, row in enumerate(recipe_lines, start=2):
        ws2.append(list(row))
        ws2[f"E{idx}"].number_format = "0.00"
        ws2[f"F{idx}"].number_format = "$#,##0.000"
        ws2[f"G{idx}"].number_format = "$#,##0.00"
        for cell in ws2[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws2, 1)
    auto_fit_columns(ws2)

    # Tab 3: 3_Menu_Engineering_Matrix
    ws3 = wb.create_sheet("3_Menu_Engineering_Matrix")
    ws3.append([
        "Menu_Item", "Category", "Current_Menu_Price", "Plate_COGS",
        "Food_Cost_Pct", "Target_COGS_Pct", "Recommended_Price",
        "Contribution_Margin", "Monthly_Units_Sold", "Total_Monthly_Profit",
        "Matrix_Quadrant"
    ])
    menu_items = [
        (
            "Cardamom Brown Sugar Latte (12oz)", "Espresso Bar", 6.25,
            "=SUMIF('2_Recipe_COGS_Calculator'!$A$2:$A$14,A2,'2_Recipe_COGS_Calculator'!$G$2:$G$14)",
            "=D2/C2", 0.22, "=D2/F2", "=C2-D2", 940, "=H2*I2",
            '=IF(AND(H2>=AVERAGE($H$2:$H$5),I2>=AVERAGE($I$2:$I$5)),"STAR (Promote)",IF(H2>=AVERAGE($H$2:$H$5),"PUZZLE (Upsell)","PLOWHORSE (Reprice)"))'
        ),
        (
            "Oat Milk Cortado (8oz)", "Espresso Bar", 5.25,
            "=SUMIF('2_Recipe_COGS_Calculator'!$A$2:$A$14,A3,'2_Recipe_COGS_Calculator'!$G$2:$G$14)",
            "=D3/C3", 0.22, "=D3/F3", "=C3-D3", 620, "=H3*I3",
            '=IF(AND(H3>=AVERAGE($H$2:$H$5),I3>=AVERAGE($I$2:$I$5)),"STAR (Promote)",IF(H3>=AVERAGE($H$2:$H$5),"PUZZLE (Upsell)","PLOWHORSE (Reprice)"))'
        ),
        (
            "Sourdough Avocado & Poached Egg Toast", "All-Day Kitchen", 13.50,
            "=SUMIF('2_Recipe_COGS_Calculator'!$A$2:$A$14,A4,'2_Recipe_COGS_Calculator'!$G$2:$G$14)",
            "=D4/C4", 0.28, "=D4/F4", "=C4-D4", 480, "=H4*I4",
            '=IF(AND(H4>=AVERAGE($H$2:$H$5),I4>=AVERAGE($I$2:$I$5)),"STAR (Promote)",IF(H4>=AVERAGE($H$2:$H$5),"PUZZLE (Upsell)","PLOWHORSE (Reprice)"))'
        ),
        (
            "Saffron Garlic Gulf Shrimp Skillet", "Small Plates", 19.00,
            "=SUMIF('2_Recipe_COGS_Calculator'!$A$2:$A$14,A5,'2_Recipe_COGS_Calculator'!$G$2:$G$14)",
            "=D5/C5", 0.30, "=D5/F5", "=C5-D5", 310, "=H5*I5",
            '=IF(AND(H5>=AVERAGE($H$2:$H$5),I5>=AVERAGE($I$2:$I$5)),"STAR (Promote)",IF(H5>=AVERAGE($H$2:$H$5),"PUZZLE (Upsell)","PLOWHORSE (Reprice)"))'
        ),
    ]
    for idx, row in enumerate(menu_items, start=2):
        ws3.append(list(row))
        ws3[f"C{idx}"].number_format = "$#,##0.00"
        ws3[f"D{idx}"].number_format = "$#,##0.00"
        ws3[f"E{idx}"].number_format = "0.0%"
        ws3[f"F{idx}"].number_format = "0.0%"
        ws3[f"G{idx}"].number_format = "$#,##0.00"
        ws3[f"H{idx}"].number_format = "$#,##0.00"
        ws3[f"I{idx}"].number_format = "#,##0"
        ws3[f"J{idx}"].number_format = "$#,##0.00"
        for cell in ws3[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            cell.fill = GREEN_FILL if idx in (2, 4) else ACCENT_FILL

    # Summary Row
    ws3.append([
        "TOTAL / PORTFOLIO AVERAGE", "", "=AVERAGE(C2:C5)", "=AVERAGE(D2:D5)",
        "=AVERAGE(E2:E5)", "=AVERAGE(F2:F5)", "=AVERAGE(G2:G5)", "=AVERAGE(H2:H5)",
        "=SUM(I2:I5)", "=SUM(J2:J5)", ""
    ])
    for cell in ws3[6]:
        cell.font = BOLD_FONT
        cell.border = CELL_BORDER
        cell.fill = BLUE_FILL
    ws3["C6"].number_format = "$#,##0.00"
    ws3["D6"].number_format = "$#,##0.00"
    ws3["E6"].number_format = "0.0%"
    ws3["F6"].number_format = "0.0%"
    ws3["G6"].number_format = "$#,##0.00"
    ws3["H6"].number_format = "$#,##0.00"
    ws3["I6"].number_format = "#,##0"
    ws3["J6"].number_format = "$#,##0.00"

    style_sheet_headers(ws3, 1)
    auto_fit_columns(ws3)

    out_path = TMP_DIR / "Antigravity-B2B-1-Restaurant-Cafe-COGS-and-Menu-Engineering.xlsx"
    wb.save(out_path)
    print(f"Saved {out_path}")
    return out_path


def build_b2b_2_salon_barber_commission():
    wb = openpyxl.Workbook()

    # Tab 1: 1_Staff_and_Booth_Setup
    ws1 = wb.active
    ws1.title = "1_Staff_and_Booth_Setup"
    ws1.append([
        "Staff_ID", "Stylist_or_Barber_Name", "Role", "Compensation_Model",
        "Service_Commission_Pct", "Retail_Commission_Pct", "Weekly_Booth_Rent_Due",
        "Backbar_Fee_Per_Chemical_Svc", "Active_Status"
    ])
    staff = [
        ("STF-01", "Elena Vance", "Senior Colorist & Owner", "Commission", 0.60, 0.15, 0.00, 8.00, "Active"),
        ("STF-02", "Maya Lin", "Lead Nail & Botanical Specialist", "Commission", 0.50, 0.12, 0.00, 4.00, "Active"),
        ("STF-03", "Marcus Cole", "Master Barber", "Commission", 0.55, 0.15, 0.00, 2.00, "Active"),
        ("STF-04", "Devon Brooks", "Independent Chair / Booth Renter", "Booth Rent", 1.00, 0.20, 275.00, 0.00, "Active"),
        ("STF-05", "Chloe Bennett", "Junior Stylist", "Commission", 0.45, 0.10, 0.00, 6.00, "Active"),
    ]
    for idx, row in enumerate(staff, start=2):
        ws1.append(list(row))
        ws1[f"E{idx}"].number_format = "0.0%"
        ws1[f"F{idx}"].number_format = "0.0%"
        ws1[f"G{idx}"].number_format = "$#,##0.00"
        ws1[f"H{idx}"].number_format = "$#,##0.00"
        for cell in ws1[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws1, 1)
    auto_fit_columns(ws1)

    # Tab 2: 2_Daily_Service_and_Tip_Log
    ws2 = wb.create_sheet("2_Daily_Service_and_Tip_Log")
    ws2.append([
        "Ticket_ID", "Date", "Staff_ID", "Stylist_or_Barber_Name",
        "Service_Category", "Service_Description", "Gross_Service_Rev",
        "Chemical_or_Backbar_Units", "Retail_Product_Sales", "Card_Tip_Amount",
        "Payment_Method"
    ])
    tickets = [
        ("TKT-1001", "2026-11-10", "STF-01", "Elena Vance", "Color & Gloss", "Full Balayage + Bond Builder", 215.00, 2, 48.00, 43.00, "Card"),
        ("TKT-1002", "2026-11-10", "STF-02", "Maya Lin", "Nails & Soak", "Structured Gel Manicure + Cedar Soak", 95.00, 1, 24.00, 20.00, "Card"),
        ("TKT-1003", "2026-11-11", "STF-03", "Marcus Cole", "Barbering", "Skin Fade + Hot Towel Razor Shave", 68.00, 1, 22.00, 15.00, "Card"),
        ("TKT-1004", "2026-11-11", "STF-04", "Devon Brooks", "Barbering", "Classic Scissor Cut & Beard Trim", 55.00, 0, 18.00, 12.00, "House POS"),
        ("TKT-1005", "2026-11-12", "STF-01", "Elena Vance", "Cut & Style", "Precision Cut + Botanical Blowout", 95.00, 0, 36.00, 20.00, "Card"),
        ("TKT-1006", "2026-11-12", "STF-05", "Chloe Bennett", "Color & Gloss", "Root Touch-Up + Express Gloss", 135.00, 1, 28.00, 27.00, "Card"),
        ("TKT-1007", "2026-11-13", "STF-02", "Maya Lin", "Nails & Soak", "Spa Pedicure + Callus Treatment", 78.00, 1, 0.00, 16.00, "Card"),
        ("TKT-1008", "2026-11-14", "STF-03", "Marcus Cole", "Barbering", "Executive Cut + Beard Sculpt", 62.00, 0, 26.00, 14.00, "Card"),
        ("TKT-1009", "2026-11-14", "STF-04", "Devon Brooks", "Barbering", "Taper Fade + Lineup", 45.00, 0, 0.00, 10.00, "House POS"),
        ("TKT-1010", "2026-11-15", "STF-05", "Chloe Bennett", "Cut & Style", "Signature Wash, Cut & Style", 75.00, 0, 32.00, 15.00, "Card"),
    ]
    for idx, row in enumerate(tickets, start=2):
        ws2.append(list(row))
        ws2[f"G{idx}"].number_format = "$#,##0.00"
        ws2[f"I{idx}"].number_format = "$#,##0.00"
        ws2[f"J{idx}"].number_format = "$#,##0.00"
        for cell in ws2[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws2, 1)
    auto_fit_columns(ws2)

    # Tab 3: 3_Commission_Payout_Summary
    ws3 = wb.create_sheet("3_Commission_Payout_Summary")
    ws3.append([
        "Staff_ID", "Stylist_or_Barber_Name", "Comp_Model",
        "Gross_Service_Rev", "Service_Comm_Earned", "Retail_Sales",
        "Retail_Comm_Earned", "Card_Tips_Collected", "Backbar_Deduction",
        "Booth_Rent_Deduction", "Net_Staff_Payout", "House_Net_Retained"
    ])
    for idx in range(2, 7):
        ws3.append([
            f"='1_Staff_and_Booth_Setup'!A{idx}",
            f"='1_Staff_and_Booth_Setup'!B{idx}",
            f"='1_Staff_and_Booth_Setup'!D{idx}",
            f"=SUMIF('2_Daily_Service_and_Tip_Log'!$C$2:$C$11,A{idx},'2_Daily_Service_and_Tip_Log'!$G$2:$G$11)",
            f"=D{idx}*'1_Staff_and_Booth_Setup'!E{idx}",
            f"=SUMIF('2_Daily_Service_and_Tip_Log'!$C$2:$C$11,A{idx},'2_Daily_Service_and_Tip_Log'!$I$2:$I$11)",
            f"=F{idx}*'1_Staff_and_Booth_Setup'!F{idx}",
            f"=SUMIF('2_Daily_Service_and_Tip_Log'!$C$2:$C$11,A{idx},'2_Daily_Service_and_Tip_Log'!$J$2:$J$11)",
            f"=SUMIF('2_Daily_Service_and_Tip_Log'!$C$2:$C$11,A{idx},'2_Daily_Service_and_Tip_Log'!$H$2:$H$11)*'1_Staff_and_Booth_Setup'!H{idx}",
            f"='1_Staff_and_Booth_Setup'!G{idx}",
            f"=E{idx}+G{idx}+H{idx}-I{idx}-J{idx}",
            f"=(D{idx}+F{idx})-(E{idx}+G{idx})+I{idx}+J{idx}"
        ])
        for col_let in ("D", "E", "F", "G", "H", "I", "J", "K", "L"):
            ws3[f"{col_let}{idx}"].number_format = "$#,##0.00"
        for cell in ws3[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            cell.fill = GREEN_FILL if idx != 5 else ACCENT_FILL

    # Totals row
    ws3.append([
        "TOTAL", "WEEKLY SHOP SUMMARY", "",
        "=SUM(D2:D6)", "=SUM(E2:E6)", "=SUM(F2:F6)", "=SUM(G2:G6)",
        "=SUM(H2:H6)", "=SUM(I2:I6)", "=SUM(J2:J6)", "=SUM(K2:K6)", "=SUM(L2:L6)"
    ])
    for col_let in ("D", "E", "F", "G", "H", "I", "J", "K", "L"):
        ws3[f"{col_let}7"].number_format = "$#,##0.00"
    for cell in ws3[7]:
        cell.font = BOLD_FONT
        cell.border = CELL_BORDER
        cell.fill = BLUE_FILL

    style_sheet_headers(ws3, 1)
    auto_fit_columns(ws3)

    out_path = TMP_DIR / "Antigravity-B2B-2-Salon-Barber-Commission-and-Booth-Tracker.xlsx"
    wb.save(out_path)
    print(f"Saved {out_path}")
    return out_path


def build_b2b_3_smb_historical_ledger():
    """
    100% Historical Cash & Expense Bookkeeping Ledger (Zero 'forecasting' keywords).
    """
    wb = openpyxl.Workbook()

    # Tab 1: 1_Categories_and_Accounts
    ws1 = wb.active
    ws1.title = "1_Categories_and_Accounts"
    ws1.append([
        "Category_Code", "Category_Name", "Classification", "Tax_Schedule_C_Ref",
        "Bookkeeping_Notes"
    ])
    categories = [
        ("REV-100", "In-Store & Counter Sales", "Operating Revenue", "Line 1 (Gross Receipts)", "Completed POS settlements"),
        ("REV-200", "Catering & Private Event Receipts", "Operating Revenue", "Line 1 (Gross Receipts)", "Invoiced catering & events"),
        ("COGS-300", "Food, Beverage & Retail Inventory", "Cost of Goods Sold", "Part III (Purchases)", "Wholesale inventory & ingredients"),
        ("COGS-310", "Packaging & Disposable Supplies", "Cost of Goods Sold", "Part III (Materials)", "Cups, bags, boxes, napkins"),
        ("EXP-400", "Staff Wages & Payroll Taxes", "Operating Expense", "Line 26 (Wages)", "Historical biweekly payroll"),
        ("EXP-410", "Storefront Lease & Utilities", "Operating Expense", "Line 20b / Line 25", "Rent, electric, gas, water, fiber"),
        ("EXP-420", "POS Processing & Merchant Fees", "Operating Expense", "Line 10 (Commissions/Fees)", "Card processing & software fees"),
        ("EXP-430", "Equipment Repair & Maintenance", "Operating Expense", "Line 21 (Repairs)", "Espresso machine & HVAC service"),
        ("EXP-440", "Local Marketing & Print Menus", "Operating Expense", "Line 8 (Advertising)", "Signage, flyers, website hosting"),
        ("EXP-450", "Business Insurance & Licenses", "Operating Expense", "Line 15 (Insurance)", "General liability & health permit"),
    ]
    for idx, row in enumerate(categories, start=2):
        ws1.append(list(row))
        for cell in ws1[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws1, 1)
    auto_fit_columns(ws1)

    # Tab 2: 2_Monthly_Income_Expense_Log
    ws2 = wb.create_sheet("2_Monthly_Income_Expense_Log")
    ws2.append([
        "Entry_ID", "Transaction_Date", "Month_Key", "Payee_or_Source",
        "Category_Name", "Classification", "Payment_Account",
        "Receipt_Verified", "Amount_Inflow", "Amount_Outflow", "Net_Cash_Effect"
    ])
    txns = [
        ("TX-001", "2026-10-03", "2026-10", "Square POS Weekly Settlement", "In-Store & Counter Sales", "Operating Revenue", "Operating Checking", "Yes", 14250.00, 0.00, "=I2-J2"),
        ("TX-002", "2026-10-05", "2026-10", "RoastCo & Valley Dairy Wholesale", "Food, Beverage & Retail Inventory", "Cost of Goods Sold", "Business Visa", "Yes", 0.00, 3840.00, "=I3-J3"),
        ("TX-003", "2026-10-08", "2026-10", "Harbor Properties LLC", "Storefront Lease & Utilities", "Operating Expense", "Operating Checking", "Yes", 0.00, 2950.00, "=I4-J4"),
        ("TX-004", "2026-10-15", "2026-10", "Gusto Biweekly Payroll", "Staff Wages & Payroll Taxes", "Operating Expense", "Operating Checking", "Yes", 0.00, 4620.00, "=I5-J5"),
        ("TX-005", "2026-10-18", "2026-10", "Autumn Market Catering Deposit", "Catering & Private Event Receipts", "Operating Revenue", "Operating Checking", "Yes", 2400.00, 0.00, "=I6-J6"),
        ("TX-006", "2026-10-22", "2026-10", "EcoPack Supply", "Packaging & Disposable Supplies", "Cost of Goods Sold", "Business Visa", "Yes", 0.00, 680.00, "=I7-J7"),
        ("TX-007", "2026-11-02", "2026-11", "Square POS Weekly Settlement", "In-Store & Counter Sales", "Operating Revenue", "Operating Checking", "Yes", 15680.00, 0.00, "=I8-J8"),
        ("TX-008", "2026-11-04", "2026-11", "RoastCo & Hearth Bakehouse", "Food, Beverage & Retail Inventory", "Cost of Goods Sold", "Business Visa", "Yes", 0.00, 4120.00, "=I9-J9"),
        ("TX-009", "2026-11-08", "2026-11", "Harbor Properties LLC", "Storefront Lease & Utilities", "Operating Expense", "Operating Checking", "Yes", 0.00, 2950.00, "=I10-J10"),
        ("TX-010", "2026-11-12", "2026-11", "Eva Cheeks Web Design", "Local Marketing & Print Menus", "Operating Expense", "Business Visa", "Yes", 0.00, 125.00, "=I11-J11"),
        ("TX-011", "2026-11-15", "2026-11", "Gusto Biweekly Payroll", "Staff Wages & Payroll Taxes", "Operating Expense", "Operating Checking", "Yes", 0.00, 4790.00, "=I12-J12"),
        ("TX-012", "2026-11-16", "2026-11", "Civic Chamber Breakfast Order", "Catering & Private Event Receipts", "Operating Revenue", "Operating Checking", "Yes", 1950.00, 0.00, "=I13-J13"),
    ]
    for idx, row in enumerate(txns, start=2):
        ws2.append(list(row))
        ws2[f"I{idx}"].number_format = "$#,##0.00"
        ws2[f"J{idx}"].number_format = "$#,##0.00"
        ws2[f"K{idx}"].number_format = "$#,##0.00"
        for cell in ws2[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL
    style_sheet_headers(ws2, 1)
    auto_fit_columns(ws2)

    # Tab 3: 3_Historical_P_and_L_Summary
    ws3 = wb.create_sheet("3_Historical_P_and_L_Summary")
    ws3.append([
        "Category_Name", "Classification", "Oct_2026_Actual",
        "Nov_2026_Actual", "YTD_Historical_Total", "Share_of_Total_Revenue"
    ])
    for idx, cat in enumerate(categories, start=2):
        cat_name = cat[1]
        classification = cat[2]
        is_rev = classification == "Operating Revenue"
        sum_col = "$I$2:$I$13" if is_rev else "$J$2:$J$13"
        ws3.append([
            cat_name,
            classification,
            f'=SUMIFS(\'2_Monthly_Income_Expense_Log\'!{sum_col},\'2_Monthly_Income_Expense_Log\'!$E$2:$E$13,A{idx},\'2_Monthly_Income_Expense_Log\'!$C$2:$C$13,"2026-10")',
            f'=SUMIFS(\'2_Monthly_Income_Expense_Log\'!{sum_col},\'2_Monthly_Income_Expense_Log\'!$E$2:$E$13,A{idx},\'2_Monthly_Income_Expense_Log\'!$C$2:$C$13,"2026-11")',
            f"=C{idx}+D{idx}",
            f"=E{idx}/$E$12"
        ])
        ws3[f"C{idx}"].number_format = "$#,##0.00"
        ws3[f"D{idx}"].number_format = "$#,##0.00"
        ws3[f"E{idx}"].number_format = "$#,##0.00"
        ws3[f"F{idx}"].number_format = "0.0%"
        for cell in ws3[idx]:
            cell.font = BODY_FONT
            cell.border = CELL_BORDER
            cell.fill = GREEN_FILL if is_rev else (ACCENT_FILL if "Cost of Goods" in classification else ZEBRA_FILL)

    # Summary KPI rows (Rows 12, 13, 14, 15)
    summary_rows = [
        ("TOTAL OPERATING REVENUE", "Summary KPI", "=SUM(C2:C3)", "=SUM(D2:D3)", "=C12+D12", "=E12/E12", GREEN_FILL),
        ("TOTAL COST OF GOODS SOLD (COGS)", "Summary KPI", "=SUM(C4:C5)", "=SUM(D4:D5)", "=C13+D13", "=E13/$E$12", ACCENT_FILL),
        ("GROSS PROFIT (REVENUE - COGS)", "Summary KPI", "=C12-C13", "=D12-D13", "=E12-E13", "=E14/$E$12", BLUE_FILL),
        ("TOTAL OPERATING EXPENSES", "Summary KPI", "=SUM(C6:C11)", "=SUM(D6:D11)", "=C15+D15", "=E15/$E$12", RED_FILL),
        ("HISTORICAL NET OPERATING INCOME", "Summary KPI", "=C14-C15", "=D14-D15", "=E14-E15", "=E16/$E$12", GREEN_FILL),
    ]
    for offset, srow in enumerate(summary_rows, start=12):
        ws3.append(list(srow[:6]))
        ws3[f"C{offset}"].number_format = "$#,##0.00"
        ws3[f"D{offset}"].number_format = "$#,##0.00"
        ws3[f"E{offset}"].number_format = "$#,##0.00"
        ws3[f"F{offset}"].number_format = "0.0%"
        for cell in ws3[offset]:
            cell.font = BOLD_FONT
            cell.border = CELL_BORDER
            cell.fill = srow[6]

    style_sheet_headers(ws3, 1)
    auto_fit_columns(ws3)

    out_path = TMP_DIR / "Antigravity-B2B-3-SMB-Historical-Cash-and-Expense-Ledger.xlsx"
    wb.save(out_path)
    print(f"Saved {out_path}")
    return out_path


def render_fiverr_gallery_images():
    gallery_dir = TMP_DIR / "fiverr-gallery"
    gallery_dir.mkdir(parents=True, exist_ok=True)

    slides = [
        (
            "Gig1-1-Cover.png",
            "GIG 1 · CUSTOM MOBILE-FIRST BUSINESS WEBSITES",
            "Fast, Mobile-First HTML/CSS Websites for Local Businesses",
            "Built for Restaurants, Cafes, Salons & Barbershops · No Monthly Platform Lock-In",
            "#0F172A", "#F59E0B",
            [
                ("100% Mobile-Ready", "Tested down to 320px viewports with tap-to-call, SMS text links & clean menus"),
                ("Zero Bloated Builders", "Pure semantic HTML5 & CSS3 — loads sub-second on cellular connections"),
                ("5 Live Industry Demos", "The Copper Kettle · Saffron & Salt · Harbor Street · Northgate · Linden & Stone"),
            ],
            "Packages from $45 Basic · $75 Standard · $120 Multi-Section Complete"
        ),
        (
            "Gig1-2-Restaurant-Cafe-Showcase.png",
            "RESTAURANT, CAFE & BAKERY DEMO SHOWCASE",
            "Turn Instagram & Google Map Visitors Into Diners",
            "Clear Pricing, Dietary Tags, Tap-to-Call Reservations & Hours Above the Fold",
            "#1E1B18", "#D97706",
            [
                ("The Copper Kettle", "Warm neighborhood kitchen & bakery layout with structured menu & map embed"),
                ("Saffron & Salt", "Editorial Mediterranean coastal bistro with dinner & Mezze price tiers"),
                ("Harbor Street Coffee", "Small-batch espresso bar & bakehouse with morning schedule & pastry board"),
            ],
            "Includes LocalBusiness JSON-LD Schema + OpenGraph Social Cards"
        ),
        (
            "Gig1-3-Salon-Barber-Showcase.png",
            "SALON, SPA & BARBERSHOP DEMO SHOWCASE",
            "Transparent Service Menus & Direct Booking Links",
            "Eliminate 'DM for Price' Friction With Clean Service Tiers & Staff Cards",
            "#1C2522", "#10B981",
            [
                ("Linden & Stone Salon", "Botanical hair, nail & spa menu with transparent starting prices & SMS booking"),
                ("Northgate Barber Room", "Classic neighborhood barbershop with walk-in hours, cuts & hot towel shaves"),
                ("WCAG AA Contrast Verified", "Every heading, price badge, and CTA button audited for readability"),
            ],
            "Delivered With Clean Source Files or Hosted Live on GitHub Pages"
        ),
        (
            "Gig2-1-Cover.png",
            "GIG 2 · RESTAURANT & SALON EXCEL / SHEETS TRACKERS",
            "Recipe COGS, Menu Engineering & Salon Commission Sheets",
            "Ready-to-Use Excel (.xlsx) & Google Sheets Workbooks With Live Formulas",
            "#0F291E", "#34D399",
            [
                ("Restaurant COGS & Menu Matrix", "Pack-to-portion yield math, plate COGS %, target pricing & Star/Plowhorse matrix"),
                ("Salon & Barber Payout Tracker", "Commission splits, booth rent deductions, backbar fees & card tip reconciliation"),
                ("Zero Broken Macros", "Pure, transparent Excel & Google Sheets formulas (SUMIFS, IF, INDEX) anyone can edit"),
            ],
            "Packages from $25 Starter · $50 Multi-Tab Workbook · $85 Custom Setup"
        ),
        (
            "Gig2-2-COGS-Menu-Matrix.png",
            "INSIDE WORKBOOK #1 · RESTAURANT & CAFE COGS",
            "Know Your Exact Plate Cost & Margin on Every Item",
            "3 Linked Tabs: 1_Ingredient_Master -> 2_Recipe_COGS_Calculator -> 3_Menu_Engineering_Matrix",
            "#1E293B", "#38BDF8",
            [
                ("Trim & Yield Adjusted", "Automatically converts 5lb bags or 4-gallon cases into exact per-oz recipe costs"),
                ("Target Food Cost % Alerts", "Compare actual plate COGS % against your 22%–30% target threshold instantly"),
                ("Auto-Classified Quadrants", "Flags every menu item as STAR, PLOWHORSE, PUZZLE, or DOG based on margin & volume"),
            ],
            "Compatible With Microsoft Excel 2019+/365 & Google Sheets"
        ),
        (
            "Gig2-3-Salon-Commission-Tracker.png",
            "INSIDE WORKBOOK #2 · SALON & BARBER PAYOUTS",
            "Close Weekly Payroll & Booth Rent in 5 Minutes",
            "3 Linked Tabs: 1_Staff_and_Booth_Setup -> 2_Daily_Service_and_Tip_Log -> 3_Commission_Payout_Summary",
            "#27173A", "#C084FC",
            [
                ("Hybrid Shop Ready", "Supports both % Commission Stylists and Fixed Weekly Booth Renters in one sheet"),
                ("Backbar & Chemical Deductions", "Automatically deducts per-service color/chemical bowl fees before payout"),
                ("Retail Bonus & Card Tips", "Separates service commission, retail product tiers, and pass-through card tips"),
            ],
            "Built for Salons, Barbershops, Nail Studios & Med-Spas"
        ),
        (
            "Gig3-1-Cover.png",
            "GIG 3 · HISTORICAL BOOKKEEPING & EXPENSE LEDGERS",
            "Clean Monthly Income & Expense Ledgers in Excel & Sheets",
            "Organize Past Receipts, POS Settlements & Schedule C Categories Without Messy Software",
            "#1E293B", "#FBBF24",
            [
                ("100% Historical Bookkeeping", "Structured past-period cash inflow/outflow tracking and monthly P&L summaries"),
                ("Tax-Ready Categorization", "Mapped directly to standard Schedule C expense lines for clean CPA handoff"),
                ("Multi-Account Reconciliation", "Track Operating Checking, Business Credit Cards & POS payouts in one log"),
            ],
            "Packages from $20 Basic Ledger · $45 Historical P&L Pack · $75 Custom Cleanup"
        ),
        (
            "Gig3-2-Expense-Categorization.png",
            "INSIDE WORKBOOK #3 · HISTORICAL CASH & EXPENSE LOG",
            "Every Transaction Logged, Verified & Auto-Summarized",
            "3 Linked Tabs: 1_Categories_and_Accounts -> 2_Monthly_Income_Expense_Log -> 3_Historical_P_and_L_Summary",
            "#0F172A", "#2DD4BF",
            [
                ("Automated Month-by-Month Rollup", "SUMIFS formulas aggregate every logged receipt into Oct/Nov/YTD columns automatically"),
                ("Gross Profit & Operating Net", "Separates Cost of Goods Sold (COGS) from fixed overhead to show true net margin"),
                ("Receipt Audit Column", "Filter unverified transactions in seconds before handing books to your accountant"),
            ],
            "Clean Formatting · Frozen Headers · Ready for Immediate Data Entry"
        ),
        (
            "Gig3-3-Dashboard-Instructions.png",
            "WHAT YOU RECEIVE WITH EVERY ORDER",
            "Turnkey Delivery + Fast Customization Support",
            "Designed & Verified by Eva Cheeks — Practical Digital Tools for Small Business Owners",
            "#111827", "#60A5FA",
            [
                ("Unlocked .XLSX + Google Sheet", "No password-locked cells — you own 100% of the workbook and formulas forever"),
                ("Tailored to Your Categories", "We pre-load your actual menu items, staff tiers, or expense categories on request"),
                ("Fast Turnaround & Clear Walkthrough", "Includes a quick-start guide so you or your manager can use it on Day 1"),
            ],
            "Message Anytime With Your Current Menu, Price List, or CSV Export!"
        ),
    ]

    for filename, badge, title, subtitle, bg_hex, accent_hex, cards, footer_text in slides:
        html_path = gallery_dir / f"{filename}.html"
        png_path = gallery_dir / filename
        cards_html = "".join(
            f"""
            <div class="card">
              <div class="card-title">{c_title}</div>
              <div class="card-body">{c_body}</div>
            </div>
            """
            for c_title, c_body in cards
        )
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1280px;
    height: 769px;
    overflow: hidden;
    background: radial-gradient(circle at 85% 15%, #334155 0%, {bg_hex} 70%);
    color: #F8FAFC;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 54px 64px;
  }}
  .top-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .badge {{
    display: inline-block;
    background: rgba(255,255,255,0.08);
    border: 1.5px solid {accent_hex};
    color: {accent_hex};
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding: 8px 18px;
    border-radius: 999px;
    text-transform: uppercase;
  }}
  .brand {{
    font-size: 18px;
    font-weight: 700;
    color: #CBD5E1;
    letter-spacing: 0.5px;
  }}
  .hero {{
    margin-top: 12px;
  }}
  h1 {{
    font-size: 46px;
    line-height: 1.15;
    font-weight: 800;
    color: #FFFFFF;
    margin-bottom: 14px;
    max-width: 1080px;
  }}
  .subtitle {{
    font-size: 22px;
    color: #CBD5E1;
    font-weight: 500;
    max-width: 980px;
  }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    margin: 24px 0;
  }}
  .card {{
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-top: 5px solid {accent_hex};
    border-radius: 16px;
    padding: 28px 26px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
  }}
  .card-title {{
    font-size: 22px;
    font-weight: 800;
    color: {accent_hex};
    margin-bottom: 12px;
  }}
  .card-body {{
    font-size: 17px;
    line-height: 1.5;
    color: #E2E8F0;
  }}
  .footer {{
    background: rgba(255, 255, 255, 0.07);
    border-left: 6px solid {accent_hex};
    padding: 18px 26px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .footer-text {{
    font-size: 20px;
    font-weight: 700;
    color: #FFFFFF;
  }}
  .footer-url {{
    font-size: 17px;
    font-weight: 600;
    color: {accent_hex};
  }}
</style>
</head>
<body>
  <div class="top-bar">
    <span class="badge">{badge}</span>
    <span class="brand">EVA CHEEKS · DIGITAL STUDIO</span>
  </div>
  <div class="hero">
    <h1>{title}</h1>
    <div class="subtitle">{subtitle}</div>
  </div>
  <div class="cards">
    {cards_html}
  </div>
  <div class="footer">
    <span class="footer-text">{footer_text}</span>
    <span class="footer-url">evacheecks.github.io</span>
  </div>
</body>
</html>
"""
        html_path.write_text(html_content, encoding="utf-8")
        subprocess.run(
            [
                "chromium",
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--window-size=1280,769",
                f"--screenshot={png_path}",
                f"file://{html_path}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        html_path.unlink(missing_ok=True)
        print(f"Rendered {png_path} (1280x769)")

    zip_path = TMP_DIR / "Antigravity-Fiverr-Gallery-Images-1280x769.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for png in sorted(gallery_dir.glob("*.png")):
            zf.write(png, arcname=png.name)
    print(f"Packaged 9 PNGs into {zip_path}")
    return zip_path


if __name__ == "__main__":
    build_crm_workbook()
    build_b2b_1_restaurant_cogs()
    build_b2b_2_salon_barber_commission()
    build_b2b_3_smb_historical_ledger()
    render_fiverr_gallery_images()
