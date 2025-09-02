import pandas as pd
import PyPDF2
import re
import os
from typing import List, Dict

def fix_category_name(word: str) -> str:
    """Fix common PDF extraction errors in category names"""
    category_fixes = {
        'SDEFRSEBC': 'DEFRSEBCS',
        'SEWS': 'EWS', 
        'SORPHAN': 'ORPHAN',
        'SDEFRSCS': 'DEFRSCS',
        'SDEFROBCS': 'DEFROBCS',
        'SDEFRNT1S': 'DEFRNT1S',
        'SDEFRNT2S': 'DEFRNT2S',
        'SDEFRNT3S': 'DEFRNT3S'
    }
    
    if word in category_fixes:
        return category_fixes[word]
    elif word.startswith('S') and len(word) > 4 and word not in ['STAGE', 'STATE', 'STATUS']:
        # Handle cases where 'S' is prepended incorrectly
        potential_fix = word[1:]  # Remove leading 'S'
        if re.match(r'^[A-Z]{2,}\d*[HOS]?$', potential_fix):
            return potential_fix
    
    return word

def parse_cutoff_page_complete(text: str) -> List[Dict]:
    """Complete parser that handles ALL page structures: simple tables and multi-section pages"""
    lines = text.split('\n')
    records = []
    
    # Extract institute information
    institute_code = None
    institute_name = None
    
    for line in lines:
        line = line.strip()
        if re.match(r'^\d{5} - ', line):
            parts = line.split(' - ', 1)
            institute_code = parts[0]
            institute_name = parts[1] if len(parts) > 1 else ""
            break
    
    if not institute_code:
        return records
    
    # Find ALL courses and their positions
    courses = []
    course_positions = {}
    
    for i, line in enumerate(lines):
        line = line.strip()
        if re.match(r'^\d{10} - ', line):
            parts = line.split(' - ', 1)
            course_code = parts[0]
            course_name = parts[1] if len(parts) > 1 else ""
            courses.append((course_code, course_name))
            course_positions[course_code] = i
    
    if not courses:
        return records
    
    # Process each course section
    for course_idx, (course_code, course_name) in enumerate(courses):
        course_start = course_positions[course_code]
        
        # Find course section end
        course_end = len(lines)
        if course_idx + 1 < len(courses):
            next_course_code = courses[course_idx + 1][0]
            course_end = course_positions[next_course_code]
        
        # Get the complete course section
        course_section = lines[course_start:course_end]
        
        # Check if this is a multi-section page or simple table page
        has_sections = any('Home University Seats Allotted' in line for line in course_section)
        
        if has_sections:
            # Parse multi-section format
            records.extend(parse_multi_section_course(course_section, institute_code, institute_name, course_code, course_name))
        else:
            # Parse simple table format (original logic)
            records.extend(parse_simple_table_course(course_section, institute_code, institute_name, course_code, course_name))
    
    return records

def parse_simple_table_course(course_section: List[str], institute_code: str, institute_name: str, course_code: str, course_name: str) -> List[Dict]:
    """Parse simple table format (original logic)"""
    records = []
    all_categories = []
    data_start_idx = -1
    
    # Find the main category header line
    for i, line in enumerate(course_section):
        line = line.strip()
        if ('GOPENS' in line or 'GOPENH' in line) and len(line.split()) >= 8:
            # Add all categories from main header line
            for word in line.split():
                corrected_word = fix_category_name(word)
                if ((re.match(r'^[A-Z]{2,}\d*[HOS]?$', corrected_word) and len(corrected_word) >= 2) or
                    corrected_word == 'EWS'):
                    all_categories.append(corrected_word)
            
            # Collect additional category lines
            j = i + 1
            while j < len(course_section):
                next_line = course_section[j].strip()
                
                # Stop if we hit data lines
                if (re.search(r'\(\d+\.\d+\)', next_line) or
                    next_line.startswith('I ') or
                    len(next_line) == 0):
                    data_start_idx = j
                    break
                
                # Stop if we hit structural elements
                if (next_line.startswith('Home') or
                    next_line.startswith('Other') or
                    next_line.startswith('State')):
                    data_start_idx = j
                    break
                
                # Process this line for additional categories
                words = next_line.split() if next_line.split() else [next_line]
                for word in words:
                    corrected_word = fix_category_name(word)
                    if ((re.match(r'^[A-Z]{2,}\d*[HOS]?$', corrected_word) and len(corrected_word) >= 2) or
                        corrected_word == 'EWS'):
                        all_categories.append(corrected_word)
                
                j += 1
            
            break  # Found main category line, stop looking
    
    if not all_categories:
        return records
    
    # Extract percentiles from data section
    percentiles = []
    if data_start_idx != -1:
        for i in range(data_start_idx, len(course_section)):
            line = course_section[i].strip()
            
            # Extract percentiles from this line (including lines with 'Stage')
            paren_percentiles = re.findall(r'\(([0-9]+\.?[0-9]+)\)', line)
            for p in paren_percentiles:
                try:
                    val = float(p)
                    if 0 <= val <= 100:
                        percentiles.append(val)
                except ValueError:
                    continue
            
            # Stop conditions AFTER extracting data
            if (not line or
                line.startswith('Home University') or
                line.startswith('Other Than') or
                line.startswith('State') or
                'Stage' in line):
                break
    
    # Create records for ALL categories
    for i, category in enumerate(all_categories):
        percentile = percentiles[i] if i < len(percentiles) else None
        record = {
            'Institute_Code': institute_code,
            'Institute_Name': institute_name,
            'Course_Code': course_code,
            'Course': course_name,
            'Category': category,
            'Percentile': percentile
        }
        records.append(record)
    
    return records

def parse_multi_section_course(course_section: List[str], institute_code: str, institute_name: str, course_code: str, course_name: str) -> List[Dict]:
    """Parse multi-section format with Home University, Other sections, State Level"""
    records = []
    i = 0
    
    while i < len(course_section):
        line = course_section[i].strip()
        
        # Identify section headers
        if ('Home University Seats Allotted to Home University' in line or
            'Home University Seats Allotted to Other Than Home University' in line or
            'Other Than Home University Seats Allotted to Other Than Home University' in line or
            line == 'State Level'):
            
            # Parse this specific section
            section_categories = []
            section_percentiles = []
            
            # Find categories in next lines
            j = i + 1
            while j < len(course_section):
                cat_line = course_section[j].strip()
                
                # Stop if we hit data or another section
                if (cat_line.startswith('I ') or 
                    re.search(r'\(\d+\.\d+\)', cat_line) or
                    'Home University Seats Allotted' in cat_line or
                    cat_line == 'State Level' or
                    'Other Than Home University Seats Allotted' in cat_line or
                    'Legends:' in cat_line):
                    break
                
                # Extract categories from this line
                if cat_line:
                    words = cat_line.split()
                    for word in words:
                        corrected_word = fix_category_name(word)
                        if ((re.match(r'^[A-Z]{2,}\d*[HOS]?$', corrected_word) and len(corrected_word) >= 2) or
                            corrected_word == 'EWS'):
                            section_categories.append(corrected_word)
                j += 1
            
            # Find data for this section
            while j < len(course_section):
                data_line = course_section[j].strip()
                
                # Extract percentiles
                paren_percentiles = re.findall(r'\(([0-9]+\.?[0-9]+)\)', data_line)
                for p in paren_percentiles:
                    try:
                        val = float(p)
                        if 0 <= val <= 100:
                            section_percentiles.append(val)
                    except ValueError:
                        continue
                
                # Stop at Stage or next section
                if ('Stage' in data_line or
                    'Home University Seats Allotted' in data_line or
                    data_line == 'State Level' or
                    'Other Than Home University Seats Allotted' in data_line or
                    'Legends:' in data_line):
                    break
                j += 1
            
            # Create records for this section
            for k, category in enumerate(section_categories):
                percentile = section_percentiles[k] if k < len(section_percentiles) else None
                record = {
                    'Institute_Code': institute_code,
                    'Institute_Name': institute_name,
                    'Course_Code': course_code,
                    'Course': course_name,
                    'Category': category,
                    'Percentile': percentile
                }
                records.append(record)
            
            # Move to after this section
            i = j
        else:
            i += 1
    
    return records

def convert_pdf_sample(pdf_path: str, max_pages: int = 5):
    """Convert a small sample to test the parsing"""
    print(f"Testing parser on first {max_pages} pages...")
    
    all_records = []
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        for page_num in range(min(max_pages, len(pdf_reader.pages))):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            
            # Debug the page content
            debug_page_content(text, page_num + 1)
            
            # Try to parse
            records = parse_cutoff_page_improved(text)
            all_records.extend(records)
            
            print(f"Page {page_num + 1}: Found {len(records)} records")
            for record in records[:3]:  # Show first 3 records
                print(f"  -> {record}")
    
    return all_records

def full_conversion(pdf_path: str, csv_path: str, max_pages: int = None):
    """Full conversion with enhanced error handling and logging"""
    print(f"Starting full conversion...")
    
    all_records = []
    failed_pages = []
    page_stats = []
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        total_pages = len(pdf_reader.pages)
        
        if max_pages is None:
            max_pages = total_pages
        
        pages_to_process = min(max_pages, total_pages)
        
        for page_num in range(pages_to_process):
            if page_num % 100 == 0:  # Progress update every 100 pages
                print(f"Processing page {page_num + 1}/{pages_to_process}...")
            
            try:
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                
                if not text or len(text.strip()) < 50:
                    failed_pages.append((page_num + 1, "Empty or too short page content"))
                    continue
                
                records = parse_cutoff_page_complete(text)
                all_records.extend(records)
                
                # Track page statistics
                page_stats.append({
                    'page': page_num + 1,
                    'records': len(records)
                })
                
                # Log pages with no records for investigation
                if len(records) == 0:
                    failed_pages.append((page_num + 1, "No records extracted"))
                    
            except Exception as e:
                failed_pages.append((page_num + 1, f"Exception: {str(e)}"))
                continue
    
    # Report statistics
    if page_stats:
        successful_pages = len([p for p in page_stats if p['records'] > 0])
        total_records_per_page = [p['records'] for p in page_stats]
        avg_records = sum(total_records_per_page) / len(total_records_per_page) if total_records_per_page else 0
        
        print(f"\n📊 Processing Statistics:")
        print(f"   Pages processed: {len(page_stats)}")
        print(f"   Pages with data: {successful_pages}")
        print(f"   Pages with issues: {len(failed_pages)}")
        print(f"   Average records per page: {avg_records:.1f}")
        
        if failed_pages:
            print(f"\n⚠️  Pages with issues (first 10):")
            for page, reason in failed_pages[:10]:
                print(f"   Page {page}: {reason}")
    
    if all_records:
        df = pd.DataFrame(all_records)
        df = df.drop_duplicates()
        df = df.sort_values(['Institute_Code', 'Course_Code', 'Category'])
        
        df.to_csv(csv_path, index=False)
        
        print(f"\n✅ Conversion successful!")
        print(f"📄 Total Records: {len(df)}")
        print(f"📄 Unique Institutes: {df['Institute_Code'].nunique()}")
        print(f"📄 Unique Courses: {df['Course_Code'].nunique()}")
        print(f"📄 Unique Categories: {df['Category'].nunique()}")
        
        # Show category distribution
        print(f"\n📊 Category distribution:")
        category_counts = df['Category'].value_counts().head(10)
        for cat, count in category_counts.items():
            print(f"   {cat}: {count}")
        
        print(f"\n📋 Sample data:")
        print(df.head(10).to_string(index=False))
        
        return True
    else:
        print("❌ No records found")
        return False

def main():
    pdf_file = "CutOff.pdf"
    csv_file = "cutoff_data.csv"
    
    if not os.path.exists(pdf_file):
        print(f"❌ PDF file not found: {pdf_file}")
        return
    
    print("🚀 Starting full PDF conversion...")
    print("📄 This will process all 1590 pages and may take a few minutes.")
    
    # Run full conversion directly
    success = full_conversion(pdf_file, csv_file, max_pages=None)
    
    if success:
        print(f"\n🎉 Conversion completed successfully!")
        print(f"📁 Output file: {csv_file}")
    else:
        print(f"\n❌ Conversion failed!")

if __name__ == "__main__":
    main()
