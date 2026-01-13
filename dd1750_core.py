"""DD1750 core - Robust with debug logging."""

import io
import math
import re
import sys
from dataclasses import dataclass
from typing import List

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import letter


PAGE_W, PAGE_H = letter

# Column positions
X_BOX_L, X_BOX_R = 44.0, 88.0
X_CONTENT_L, X_CONTENT_R = 88.0, 365.0
X_UOI_L, X_UOI_R = 365.0, 408.5
X_INIT_L, X_INIT_R = 408.5, 453.5
X_SPARES_L, X_SPARES_R = 453.5, 514.5
X_TOTAL_L, X_TOTAL_R = 514.5, 566.0

Y_TABLE_TOP = 616.0
Y_TABLE_BOTTOM = 89.5
ROWS_PER_PAGE = 18
ROW_H = (Y_TABLE_TOP - Y_TABLE_BOTTOM) / ROWS_PER_PAGE
PAD_X = 3.0


@dataclass
class BomItem:
    line_no: int
    description: str
    nsn: str
    qty: int


def extract_items_from_pdf(pdf_path: str, start_page: int = 0) -> List[BomItem]:
    items = []
    
    try:
        print(f"DEBUG: Opening {pdf_path}")
        sys.stdout.flush()
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages[start_page:]):
                tables = page.extract_tables()
                
                print(f"DEBUG: Page {page_num} - Found {len(tables)} tables")
                
                for table_num, table in enumerate(tables):
                    if len(table) < 2:
                        print(f"DEBUG:   Table {table_num} skipped (too short)")
                        continue
                    
                    print(f"DEBUG:   Table {table_num} - Header: {table[0]}")
                    
                    header = table[0]
                    lv_idx = desc_idx = mat_idx = auth_idx = -1
                    
                    for i, cell in enumerate(header):
                        if cell:
                            text = str(cell).upper()
                            if 'LV' in text or 'LEVEL' in text:
                                lv_idx = i
                            elif 'DESC' in text or 'NOMENCLATURE' in text or 'PART NO.' in text:
                                desc_idx = i
                            elif 'MATERIAL' in text:
                                mat_idx = i
                            elif 'AUTH' in text and 'QTY' in text:
                                auth_idx = i
                            elif 'OH' in text and 'QTY' in text:
                                auth_idx = i
                    
                    print(f"DEBUG:   Table {table_num} - Identified columns: LV:{lv_idx}, DESC:{desc_idx}, MAT:{mat_idx}, AUTH:{auth_idx}")
                    
                    if lv_idx == -1 or desc_idx == -1:
                        print(f"DEBUG:   Table {table_num} - Skipped (no LV or DESC)")
                        continue
                    
                    for row_num, row in enumerate(table[1:]):
                        if not any(cell for cell in row if cell):
                            print(f"DEBUG:   Table {table_num} - Row {row_num} - Empty (skipped)")
                            continue
                        
                        # Check Level
                        lv_cell = row[lv_idx] if lv_idx < len(row) else None
                        if lv_cell:
                            lv_text = str(lv_cell).strip()
                            # Relaxed check - just check if it starts with B or is not empty
                            is_b_item = lv_text and ('B' in lv_text.upper() or not lv_text)
                            if not is_b_item:
                                print(f"DEBUG:   Table {table_num} - Row {row_num} - Skipped (LV is not 'B': '{lv_text}')")
                                continue
                        else:
                            print(f"DEBUG:   Table {table_num} - Row {row_num} - LV is 'B' (valid)")
                        else:
                            print(f"DEBUG:   Table {table_num} - Row {row_num} - Skipped (No LV cell)")
                            continue
                        
                        # Get Description
                        desc_cell = row[desc_idx] if desc_idx < len(row) else None
                        description = ""
                        if desc_cell:
                            text = str(desc_cell).strip()
                            # Split by newline
                            lines = text.split('\n')
                            
                            if len(lines) >= 2:
                                # Multi-line (BCP style)
                                description = lines[1].strip()
                            else:
                                # Single-line or Handwritten
                                description = lines[0].strip()
                            
                            # Cleanup
                            if '(' in description:
                                description = description.split('(')[0].strip()
                            
                            # Remove trailing codes
                            description = re.sub(r'\s+(WTY|ARC|CIIC|UI|SCMC|EA|AY|9K|9G)$', '', description, flags=re.IGNORECASE)
                            description = re.sub(r'\s+', ' ', description).strip()
                            
                            print(f"DEBUG:   Table {table_num} - Row {row_num} - Desc: '{description[:30]}...'")
                        
                        if not description:
                            print(f"DEBUG:   Table {table_num} - Row {row_num} - Skipped (Desc too short/empty)")
                            continue
                        
                        # Get NSN
                        nsn = ""
                        if mat_idx > -1:
                            mat_cell = row[mat_idx]
                            if mat_cell:
                                match = re.search(r'\b(\d{9})\b', str(mat_cell))
                                if match:
                                    nsn = match.group(1)
                        
                        # Get Quantity
                        qty = 1
                        if auth_idx > -1:
                            qty_cell = row[auth_idx]
                            if qty_cell:
                                match = re.search(r'(\d+)', str(qty_cell))
                                if match:
                                    qty = int(match.group(1))
                        else:
                            # Try OH QTY
                            oh_qty_idx = -1
                            for i, cell in enumerate(header):
                                if cell and 'OH' in str(cell).upper() and 'QTY' in str(cell).upper():
                                    oh_qty_idx = i
                            if oh_qty_idx > -1:
                                qty_cell = row[oh_qty_idx]
                                if qty_cell:
                                    match = re.search(r'(\d+)', str(qty_cell))
                                    if match:
                                        qty = int(match.group(1))
                        
                        # Add item
                        items.append(BomItem(
                            line_no=len(items) + 1,
                            description=description[:100],
                            nsn=nsn,
                            qty=qty
                        ))
                        print(f"DEBUG:   Table {table_num} - Row {row_num} - Added item {len(items)}")
    
    except Exception as e:
        print(f"CRITICAL ERROR in extraction: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []
    
    print(f"DEBUG: Total items extracted: {len(items)}")
    sys.stdout.flush()
    return items


def generate_dd1750_from_pdf(bom_path: str, template_path: str, out_path: str):
    items = extract_items_from_pdf(bom_path)
    
    print(f"DEBUG: Generating DD1750 with {len(items)} items")
    sys.stdout.flush()
    
    if not items:
        # Fallback: Always create a file
        reader = PdfReader(template_path)
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        with open(out_path, 'wb') as f:
            writer.write(f)
        print(f"DEBUG: Wrote fallback template to {out_path}")
        sys.stdout.flush()
        return out_path, 0
    
    total_pages = math.ceil(len(items) / ROWS_PER_PAGE)
    writer = PdfWriter()
    template = PdfReader(template_path)
    
    for page_num in range(total_pages):
        start_idx = page_num * ROWS_PER_PAGE
        end_idx = min((page_num + 1) * ROWS_PER_PAGE, len(items))
        page_items = items[start_idx:end_idx]
        
        print(f"DEBUG: Writing page {page_num} with {len(page_items)} items")
        
        # Create overlay
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        first_row = Y_TABLE_TOP - 5.0
        
        for i, item in enumerate(page_items):
            y = first_row - (i * ROW_H)
            
            c.setFont("Helvetica", 8)
            c.drawCentredString((X_BOX_L + X_BOX_R) / 2, y - 7, str(item.line_no))
            
            c.setFont("Helvetica", 7)
            c.drawString(X_CONTENT_L + PAD_X, y - 7, item.description[:50])
            
            if item.nsn:
                c.setFont("Helvetica", 6)
                c.drawString(X_CONTENT_L + PAD_X, y - 12, f"NSN: {item.nsn}")
            
            c.setFont("Helvetica", 8)
            c.drawCentredString((X_UOI_L + X_UOI_R) / 2, y - 7, "EA")
            c.drawCentredString((X_INIT_L + X_INIT_R) / 2, y - 7, str(item.qty))
            c.drawCentredString((X_SPARES_L + X_SPARES_R) / 2, y - 7, "0")
            c.drawCentredString((X_TOTAL_L + X_TOTAL_R) / 2, y - 7, str(item.qty))
        
        c.save()
        packet.seek(0)
        
        overlay = PdfReader(packet)
        
        # Get template page
        if page_num < len(template.pages):
            page = template.pages[page_num]
        else:
            page = template.pages[0]
        
        page.merge_page(overlay.pages[0])
        writer.add_page(page)
        print(f"DEBUG: Merged page {page_num}")
    
    # Write to file
    try:
        with open(out_path, 'wb') as f:
            writer.write(f)
        print(f"DEBUG: Successfully wrote {out_path}")
        sys.stdout.flush()
    except Exception as e:
        print(f"CRITICAL ERROR writing PDF: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Fallback
        try:
            reader = PdfReader(template_path)
            simple_writer = PdfWriter()
            simple_writer.add_page(reader.pages[0])
            with open(out_path, 'wb') as f:
                simple_writer.write(f)
            print(f"DEBUG: Wrote simple template to {out_path}")
            sys.stdout.flush()
        except:
            pass
    
    return out_path, len(items)
