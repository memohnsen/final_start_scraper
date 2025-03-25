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

def clean_categories(categories):
    """Clean up the categories field by removing extra spaces and organizing the data."""
    # Remove extra spaces
    categories = re.sub(r'\s+', ' ', categories).strip()
    
    # Split by '/' and clean each part
    parts = [part.strip() for part in categories.split('/')]
    
    # Join back with ' / ' separator
    return ' / '.join(parts)

def parse_start_list(text):
    """Parse the extracted text to identify competitors and their information."""
    entries = []
    
    # Split text into lines for processing
    lines = text.split('\n')
    
    # Skip header lines
    start_processing = False
    header_seen = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Skip header lines and "Start List presented by:" lines
        if "Lot First Name Last Name State Age Club Name Gender Event CATEGORIES Group Entry Total Session Platform Day Lifting Time" in line:
            header_seen = True
            start_processing = True
            continue
        
        if "Start List presented by:" in line:
            continue
            
        if not start_processing and not header_seen:
            continue
        
        # Parse competitor information
        # The pattern appears to be:
        # Lot# FirstName LastName State Age ClubName Gender CATEGORIES ... Group EntryTotal Session Platform Day Time
        
        # Check if the line starts with a number (Lot number)
        match = re.match(r'^(\d+)', line)
        if match:
            lot_number = match.group(1)
            
            # Extract the rest of the line after the lot number
            rest_of_line = line[len(lot_number):].strip()
            
            # Find the state (2-letter code) pattern
            state_match = re.search(r'\s([A-Z]{2})\s', rest_of_line)
            if state_match:
                state_index = rest_of_line.find(state_match.group(0))
                state = state_match.group(1)
                
                # Extract name (everything before state)
                name = rest_of_line[:state_index].strip()
                
                # Extract the rest after state
                rest_after_state = rest_of_line[state_index + len(state_match.group(0)):].strip()
                
                # Find the age (1-2 digits)
                age_match = re.match(r'(\d{1,2})', rest_after_state)
                if age_match:
                    age = age_match.group(1)
                    
                    # Extract the rest after age
                    rest_after_age = rest_after_state[len(age):].strip()
                    
                    # Find the gender (M or W) which is followed by categories
                    gender_match = re.search(r'\s([MW])\s', rest_after_age)
                    if gender_match:
                        gender_index = rest_after_age.find(gender_match.group(0))
                        
                        # Extract club name (everything before gender)
                        club = rest_after_age[:gender_index].strip()
                        
                        # Extract the rest after gender
                        rest_after_gender = rest_after_age[gender_index + len(gender_match.group(0)):].strip()
                        
                        # Find the group (A, B, C, D) which is preceded by a /
                        group_match = re.search(r'/\s+([A-Z])\s+', rest_after_gender)
                        if group_match:
                            group_index = rest_after_gender.find(group_match.group(0))
                            
                            # Extract categories (everything before group)
                            categories = rest_after_gender[:group_index].strip()
                            categories = clean_categories(categories)
                            
                            # Extract group and the rest
                            group = group_match.group(1)
                            rest_after_group = rest_after_gender[group_index + len(group_match.group(0)):].strip()
                            
                            # Split the remaining parts for entry total, session, platform, day, and time
                            parts = rest_after_group.split()
                            if len(parts) >= 5:  # We need at least 5 parts: entry_total, session, platform, day, time
                                entryTotal = parts[0]
                                
                                # Parse session and platform from combined field (e.g., "1RED")
                                session_platform = parts[1]
                                session_match = re.match(r'(\d+)([A-Za-z]+)', session_platform)
                                if session_match:
                                    session = session_match.group(1)
                                    platform = session_match.group(2).capitalize()  # Convert to proper case (e.g., "Red" not "RED")
                                else:
                                    session = session_platform
                                    platform = ""
                                
                                day = parts[2]
                                time = ' '.join(parts[3:])
                                
                                # Create entry dictionary
                                entry = {
                                    'lot_number': lot_number,
                                    'name': name,
                                    'state': state,
                                    'age': age,
                                    'club': club,
                                    'gender': gender_match.group(1),
                                    'categories': categories,
                                    'group': group,
                                    'entryTotal': entryTotal,
                                    'session': session,
                                    'platform': platform,
                                    'day': day,
                                    'time': time
                                }
                                
                                entries.append(entry)
    
    return entries

def extract_weight_class(categories):
    """Extract weight class from categories field."""
    weight_classes = []
    pattern = r'([MW])\s+(\d+)'
    matches = re.finditer(pattern, categories)
    
    for match in matches:
        gender = match.group(1)
        weight = match.group(2)
        weight_classes.append(f"{gender}{weight}")
    
    return weight_classes

def extract_age_group(categories):
    """Extract age group from categories field."""
    age_groups = []
    patterns = [
        r'U13',
        r'14-15',
        r'16-17',
        r'JUNIOR',
        r'OPEN',
        r'35',
        r'40',
        r'45',
        r'50',
        r'55',
        r'60',
        r'65',
        r'70',
        r'UNI'
    ]
    
    for pattern in patterns:
        if re.search(pattern, categories):
            age_groups.append(pattern)
    
    return age_groups

def enrich_data(entries):
    """Add additional derived fields to the entries."""
    enriched_entries = []
    
    for entry in entries:
        # Create a copy of the entry
        enriched_entry = entry.copy()
        
        # Extract weight classes
        if 'categories' in entry:
            weight_classes = extract_weight_class(entry['categories'])
            if weight_classes:
                enriched_entry['weight_classes'] = weight_classes
        
        # Extract age groups
        if 'categories' in entry:
            age_groups = extract_age_group(entry['categories'])
            if age_groups:
                enriched_entry['age_groups'] = age_groups
        
        enriched_entries.append(enriched_entry)
    
    return enriched_entries

def save_to_csv(data, output_path):
    """Save the parsed data to a CSV file."""
    # Fields to exclude from output
    excluded_fields = ['lot_number', 'state', 'group', 'age_groups', 'day', 'time', 'weight_classes', 'categories']
    
    # Define platform order
    platform_order = {
        'Red': 1,
        'White': 2,
        'Blue': 3,
        'Stars': 4,
        'Stripes': 5,
        'Rogue': 6
    }
    
    # Filter out the excluded fields and rename fields
    filtered_data = []
    for entry in data:
        filtered_entry = {}
        
        # Convert gender from W/M to Female/Male
        gender = 'Female' if entry.get('gender') == 'W' else 'Male'
        
        # Extract just the weight class number that follows M## or W## and append kg
        weight_class = ''
        categories = entry.get('categories', '')
        weight_match = re.search(r'[MW]\d{2}\s+(\d{2,3}\+?)', categories)
        if weight_match:
            weight_class = weight_match.group(1) + 'kg'
        
        # Map the fields with their new names
        field_mapping = {
            'name': entry.get('name', ''),
            'age': entry.get('age', ''),
            'club': entry.get('club', ''),
            'gender': gender,
            'weight_class': weight_class,
            'entry_total': entry.get('entryTotal', ''),
            'session_number': entry.get('session', ''),
            'session_platform': entry.get('platform', ''),
            'meet': "USAW Master's Nationals"  # Add constant meet name
        }
        
        filtered_entry.update(field_mapping)
        filtered_data.append(filtered_entry)
    
    # Convert numeric fields to integers
    numeric_fields = ['entry_total', 'age', 'session_number']
    for entry in filtered_data:
        for field in numeric_fields:
            if field in entry and isinstance(entry[field], str) and entry[field].isdigit():
                entry[field] = int(entry[field])
    
    # Sort data by session number and platform
    filtered_data.sort(key=lambda x: (
        x.get('session_number', 0),
        platform_order.get(x.get('session_platform', ''), 999)
    ))
    
    # Define the exact order of columns
    fieldnames = ['name', 'age', 'club', 'gender', 'weight_class', 'entry_total', 'session_number', 'session_platform', 'meet']
    
    # Write to CSV with specified column order
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered_data)
    
    print(f"Data saved to {output_path}")

def main():
    # File paths
    pdf_path = "start-list.pdf"
    output_path = "start_list_data.csv"  # Changed extension to .csv
    
    # Extract text from PDF
    print(f"Extracting text from {pdf_path}...")
    text = extract_text_from_pdf(pdf_path)
    
    # Save raw text for debugging
    with open("raw_text.txt", "w") as f:
        f.write(text)
    print("Raw text saved to raw_text.txt")
    
    # Parse the text
    print("Parsing text...")
    parsed_data = parse_start_list(text)
    
    # Enrich the data with additional derived fields
    print("Enriching data...")
    enriched_data = enrich_data(parsed_data)
    
    # Save the parsed data to CSV
    save_to_csv(enriched_data, output_path)
    
    print(f"Successfully processed {len(enriched_data)} entries from the PDF.")

if __name__ == "__main__":
    main() 