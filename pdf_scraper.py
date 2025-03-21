import PyPDF2
import pdfplumber
import re
import json
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
        if "Lot First Name Last Name State Age Club Name Gender CATEGORIES Group Entry Total Session Platform Day Lifting Time" in line:
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

def save_to_json(data, output_path):
    """Save the parsed data to a JSON file."""
    # Fields to exclude from output
    excluded_fields = ['lot_number', 'state', 'weight_classes', 'age_groups', 'session', 'platform', 'gender', 'day', 'time']
    
    # Filter out the excluded fields
    filtered_data = []
    for entry in data:
        filtered_entry = {k: v for k, v in entry.items() if k not in excluded_fields}
        
        # Rename categories to weightClass
        if 'categories' in entry:
            filtered_entry['weightClass'] = entry['categories']
            if 'categories' in filtered_entry:
                del filtered_entry['categories']
        
        # Create nested session object with number and platform
        if 'session' in entry and 'platform' in entry:
            session_number = entry.get('session', '')
            platform_name = entry.get('platform', '')
            
            # Convert session to integer if it's a digit
            if session_number.isdigit():
                session_number = int(session_number)
                
            # Add the nested session object
            filtered_entry['session'] = {
                'number': session_number,
                'platform': platform_name
            }
        
        filtered_data.append(filtered_entry)
    
    # Convert numeric fields to integers
    numeric_fields = ['entry_total', 'age', 'entryTotal']
    for entry in filtered_data:
        for field in numeric_fields:
            if field in entry and isinstance(entry[field], str) and entry[field].isdigit():
                entry[field] = int(entry[field])
    
    # Convert session.number to integer for proper numerical sorting
    for entry in filtered_data:
        try:
            if 'session' in entry and 'number' in entry['session']:
                session_number = entry['session']['number']
                if isinstance(session_number, str) and session_number.isdigit():
                    entry['session']['number'] = int(session_number)
                entry['session_int'] = entry['session']['number'] if isinstance(entry['session']['number'], int) else 0
            else:
                entry['session_int'] = 0
        except (ValueError, AttributeError, TypeError):
            entry['session_int'] = 0
    
    # Define platform order
    platform_order = {
        'Red': 1,
        'White': 2,
        'Blue': 3,
        'Stars': 4,
        'Stripes': 5,
        'Rogue': 6
    }
    
    # Assign platform order value for sorting
    for entry in filtered_data:
        if 'session' in entry and 'platform' in entry['session']:
            platform = entry['session']['platform']
            entry['platform_order'] = platform_order.get(platform, 999)  # Default high value for unknown platforms
        else:
            entry['platform_order'] = 999
    
    # Sort data by session number first, then by platform order, then by group
    filtered_data.sort(key=lambda x: (
        x.get('session_int', 0),
        x.get('platform_order', 999),
        x.get('group', '')
    ))
    
    # Remove temporary sorting fields
    for entry in filtered_data:
        if 'session_int' in entry:
            del entry['session_int']
        if 'platform_order' in entry:
            del entry['platform_order']
    
    # Custom JSON formatting - each object on a single line with session+platform grouping
    # and TypeScript-friendly property names (without quotes)
    with open(output_path, 'w') as f:
        f.write('export const startListData = [\n')
        
        current_session_number = None
        current_platform = None
        
        for i, entry in enumerate(filtered_data):
            session_obj = entry.get('session', {})
            session_number = session_obj.get('number', 0) if isinstance(session_obj, dict) else 0
            platform = session_obj.get('platform', '') if isinstance(session_obj, dict) else ''
            
            # Add an extra newline when platform changes within the same session
            # or when session changes
            if current_platform is not None and (
                (session_number == current_session_number and platform != current_platform) or
                (session_number != current_session_number)
            ):
                f.write('\n')
            
            current_session_number = session_number
            current_platform = platform
            
            # Create TypeScript-friendly JSON (without quotes around property names)
            # Add spaces between key-value pairs for better readability
            ts_json_parts = []
            for key, value in entry.items():
                if key == 'session' and isinstance(value, dict):
                    # Format the nested session object
                    session_parts = []
                    for session_key, session_value in value.items():
                        if isinstance(session_value, str):
                            session_parts.append(f"{session_key}: \"{session_value}\"")
                        else:
                            session_parts.append(f"{session_key}: {session_value}")
                    ts_json_parts.append(f"{key}: {{ {', '.join(session_parts)} }}")
                elif isinstance(value, str):
                    # For string values, keep the quotes around the value
                    ts_json_parts.append(f"{key}: \"{value}\"")
                else:
                    ts_json_parts.append(f"{key}: {value}")
            
            ts_json_str = "{ " + ", ".join(ts_json_parts) + " }"
            
            if i < len(filtered_data) - 1:
                f.write(f"  {ts_json_str},\n")
            else:
                f.write(f"  {ts_json_str}\n")
        
        f.write(']\n')
    
    print(f"Data saved to {output_path}")

def main():
    # File paths
    pdf_path = "start-list.pdf"
    json_output = "start_list_data.ts"
    
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
    
    # Save the parsed data to JSON only
    save_to_json(enriched_data, json_output)
    
    print(f"Successfully processed {len(enriched_data)} entries from the PDF.")

if __name__ == "__main__":
    main() 