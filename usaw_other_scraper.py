import PyPDF2
import pdfplumber
import re
import json
import csv
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file using pdfplumber."""
    all_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
    
    return '\n'.join(all_text)

def format_name(name):
    """Convert 'LAST, First' to 'First Last' with proper capitalization."""
    if ',' in name:
        last, first = name.split(',', 1)
        # Properly capitalize each part
        last = last.strip().title()
        first = first.strip().title()
        return f"{first} {last}"
    return name.strip().title()

def parse_start_list(text):
    """Parse the extracted text to identify competitors and their information."""
    entries = []
    skipped = []
    
    # Skip the first few lines that contain headers
    lines = text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        if "Session Date Gndr Group Cat Lot Age Name Total Team Comps" in line:
            start_idx = i + 1
            break
    
    # Process each line
    for line in lines[start_idx:]:
        line = line.strip()
        if not line:
            continue
            
        # Skip header/schedule lines
        if any(x in line for x in ['Weigh In', 'Start', '2025 USAW', 'owlcms', 'Session Date', 'Page']):
            continue
            
        # Skip date lines
        if line.startswith(('Thu', 'Fri', 'Sat', 'Sun', 'Apr')):
            continue
            
        # Skip platform lines
        if any(x in line for x in ['RED F', 'RED M', 'BLUE F', 'BLUE M', 'WHITE F', 'WHITE M']):
            continue
            
        # Skip weight class only lines
        if re.match(r'^[WM]\d+$', line.strip()):
            continue
            
        try:
            parts = line.split()
            if len(parts) < 4:  # Need at least ID, name, total, and category
                continue
                
            entry = {}
            
            # Handle lines that start with GA or weight class
            start_idx = 0
            if parts[0] == 'GA':
                start_idx = 1
                if len(parts) > 1 and parts[1].startswith('U'):
                    start_idx = 2
            elif parts[0].startswith(('W', 'M')) or parts[0] in ['ADAP']:
                start_idx = 1
            
            # Find weight class at the start (before member ID)
            weight_found = False
            if start_idx == 0 and (parts[0].isdigit() or (parts[0].endswith('+') and parts[0][:-1].isdigit())):
                entry['weight_class'] = parts[0] + 'kg'
                start_idx = 1
                weight_found = True
            
            # Find member ID (first number after any prefix)
            member_id = None
            for i in range(start_idx, len(parts)):
                if parts[i].isdigit():
                    member_id = int(parts[i])
                    start_idx = i + 1
                    break
            
            if member_id is None:
                skipped.append(f"Skipped (no valid ID): {line}")
                continue
                
            entry['member_id'] = member_id
            
            # Find the name (contains comma)
            name_idx = None
            for i, part in enumerate(parts[start_idx:], start_idx):
                if ',' in part:
                    name_idx = i
                    break
            
            if name_idx is None:
                skipped.append(f"Skipped (no comma in name): {line}")
                continue
                
            # Get name (including any parts until we hit a number)
            name_parts = [parts[name_idx]]
            next_idx = name_idx + 1
            while next_idx < len(parts) and not any(c.isdigit() for c in parts[next_idx]):
                name_parts.append(parts[next_idx])
                next_idx += 1
            entry['name'] = format_name(' '.join(name_parts))
            
            # Get age (look for a 2-digit number near the name)
            age_found = False
            # Look before name
            for i in range(max(0, name_idx - 2), name_idx):
                if parts[i].isdigit() and 1 <= int(parts[i]) <= 99:
                    entry['age'] = int(parts[i])
                    age_found = True
                    break
            # Look after name if not found before
            if not age_found:
                for part in parts[next_idx:]:
                    if part.isdigit() and 1 <= int(part) <= 99:
                        entry['age'] = int(part)
                        age_found = True
                        break
            
            if not age_found:
                skipped.append(f"Skipped (no age found): {line}")
                continue
            
            # Get entry total (first number after name that's > 30)
            total_found = False
            for part in parts[next_idx:]:
                if part.isdigit() and 30 <= int(part) <= 400:
                    entry['entry_total'] = int(part)
                    total_found = True
                    break
            
            if not total_found:
                skipped.append(f"Skipped (no total found): {line}")
                continue
            
            # If weight class not found yet, try other approaches
            if not weight_found:
                # Approach 1: Standard format (W65, M70, etc.)
                for part in parts:
                    if part.startswith(('W', 'M')) and any(c.isdigit() for c in part):
                        entry['gender'] = 'Female' if part.startswith('W') else 'Male'
                        weight_num = ''.join(c for c in part[1:] if c.isdigit() or c == '+')
                        entry['weight_class'] = weight_num + 'kg'
                        weight_found = True
                        break
            
            # If still not found, look for weight class at the start of line
            if not weight_found:
                for part in parts[:3]:  # Check first few parts
                    if part.isdigit() or (part.endswith('+') and part[:-1].isdigit()):
                        entry['weight_class'] = part + 'kg'
                        weight_found = True
                        break
            
            if not weight_found:
                skipped.append(f"Skipped (no weight class found): {line}")
                continue
            
            # Determine gender if not already set
            if 'gender' not in entry:
                # For GA entries, try to determine gender from name or context
                if 'MILMW' in parts or any(female_name in line for female_name in [', Ms', ', Mrs', 'MISS']):
                    entry['gender'] = 'Female'
                else:
                    # Default to Male if unsure
                    entry['gender'] = 'Male'
            
            # Get club (everything between total and GA/categories)
            club_parts = []
            found_total = False
            for part in parts[next_idx:]:
                if part.isdigit() and 30 <= int(part) <= 400:
                    found_total = True
                    continue
                if found_total:
                    if part in ['GA', 'ADAP', 'MILMM', 'MILMW'] or part.startswith('U'):
                        break
                    club_parts.append(part)
            
            entry['club'] = ' '.join(club_parts).strip()
            if not entry['club']:
                entry['club'] = 'Unaffiliated'
            
            # Add empty session info
            entry['session_number'] = ''
            entry['session_platform'] = ''
            entry['meet'] = "USAW Master's Nationals"
            
            entries.append(entry)
            
        except Exception as e:
            skipped.append(f"Error parsing line: {line}\nError: {str(e)}")
            continue
    
    print(f"\nTotal entries parsed: {len(entries)}")
    print(f"Total entries skipped: {len(skipped)}")
    print("\nFirst 10 skipped entries:")
    for i, skip in enumerate(skipped[:10]):
        print(f"{i+1}. {skip}")
    
    return entries

def save_to_csv(data, output_path):
    """Save the parsed data to a CSV file."""
    # Define the exact order of columns
    fieldnames = [
        'member_id', 'name', 'age', 'club', 'gender', 'weight_class', 
        'entry_total', 'session_number', 'session_platform', 'meet'
    ]
    
    # Write to CSV
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    
    print(f"Data saved to {output_path}")

def main():
    # File paths
    pdf_path = "start-list-new.pdf"
    output_path = "start_list_new.csv"
    
    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"Error: Could not find PDF file: {pdf_path}")
        return
    
    # Extract text from PDF
    print(f"Extracting text from {pdf_path}...")
    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {str(e)}")
        return
    
    # Save raw text for debugging
    with open("raw_text.txt", "w") as f:
        f.write(text)
    print("Raw text saved to raw_text.txt")
    
    # Parse the text
    print("Parsing text...")
    parsed_data = parse_start_list(text)
    
    if not parsed_data:
        print("Error: No entries were parsed from the PDF")
        return
    
    # Save the parsed data to CSV
    save_to_csv(parsed_data, output_path)
    
    print(f"Successfully processed {len(parsed_data)} entries from the PDF.")

if __name__ == "__main__":
    main()
