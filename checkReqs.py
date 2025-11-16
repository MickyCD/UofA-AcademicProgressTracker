# GETS THE LIST OF REQUIRED COURSES IN THE CUSTOM_LEFTPAD SECTION OF THE HTML (MAY INCLUDE ANY COURSES WITHIN THIS SECTION NOT JUST REQUIRED ONES)
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup, Tag
import json
import re
import questionary
from pathlib import Path

BASE_URL = "https://calendar.ualberta.ca/"
FACULTIES_URL = "https://calendar.ualberta.ca/content.php?catoid=56&navoid=17526"

async def fetch_page_soup(page, url: str) -> BeautifulSoup:
    """Sends Playwright page to visit a URL and return a BeautifulSoup object."""
    try:
        print(f"  -> Loading: {url.split('?')[0]}...")
        await page.goto(url, wait_until="load", timeout=60000)
        await page.wait_for_timeout(1000) # Wait for JS
        html = await page.content()
        return BeautifulSoup(html, 'html.parser')
    except Exception as e:
        print(f"    -> Error loading page {url}: {e}")
        return None

def parse_menu_from_html(soup: BeautifulSoup) -> dict:
    """Parses the MAIN faculty page menu."""
    print("Getting calendar menu...")
    catalog = {}

    content_block = soup.find('td', class_='block_content')
    if not content_block:
        print("Error: Could not parse page (missing 'td.block_content').")
        return {}

    sections = content_block.find_all('div', style='padding-left: 20px') # Block with each faculty link
    
    for section in sections:
        faculty_name_tag = section.find('h2')
        if not faculty_name_tag: continue

        faculty_name = faculty_name_tag.get_text(strip=True)
        catalog[faculty_name] = {} # Holds the name of all programs

        program_lists = section.find_all('ul', class_='program-list')
        for all in program_lists:
            links = all.find_all('a', href=True)
            for link in links:
                program_name = link.get_text(strip=True)
                program_url = link.get('href')
                
                if program_url and 'preview_program.php' in program_url:
                    # Store the name and the URL to visit later
                    catalog[faculty_name][program_name] = {
                        "source_url": BASE_URL + program_url
                    }
    print("Menu parsing complete.")
    return catalog

async def scrape_required_courses(page, program_url: str) -> list:
    """
    Visits the program page and scrapes all courses found inside
    the 'Program Requirements' section.
    """
    print(f"\nScraping required courses from program page...")
    program_soup = await fetch_page_soup(page, program_url)
    
    required_courses = []
    if not program_soup:
        return required_courses

    content_block = program_soup.find('td', class_='block_content')
    if not content_block:
        print("  -> ERROR: Could not find 'td.block_content'.")
        return required_courses
            
    # 1. Find the <h2> header for "Program Requirements"
    program_req_header = None
    all_headers = content_block.find_all(['h2', 'h3']) 
    
    for header in all_headers:
        # Check their text to find the right one
        if "Program Requirements" in header.get_text(strip=True):
            program_req_header = header
            break # found it

    search_area = None
    if not program_req_header:
        print("  -> Could not find 'Program Requirements' header, searching entire page...")
        search_area = content_block # Fallback
    else:
        print("  -> Found 'Program Requirements' header.")
        # 2. Find the div.custom_leftpad_20 that follows it.
        search_area = program_req_header.find_next('div', class_='custom_leftpad_20')

    if not search_area:
        print("  -> Could not find 'custom_leftpad_20' div, searching entire page...")
        search_area = content_block # Fallback
    
    # 3. Find all 'acalog-course' links *directly within that search_area*
    #    (All "Term" logic has been removed)
    print("  -> Scraping all 'acalog-course' links inside the found section...")
    course_lis = search_area.find_all('li', class_='acalog-course')
                
    for li in course_lis:
        course_link = li.find('a')
        if course_link:
            full_text = course_link.get_text(strip=True)
            match = re.match(r'([A-Z\s]+ \d+[A-Z]?)', full_text)
            if match:
                course_code = match.group(1).strip()
                required_courses.append(course_code)
    
    print(f"  -> Found {len(required_courses)} auto-scraped courses.")
    return sorted(list(set(required_courses))) # Return a clean, sorted list

def load_user_courses(filepath: str) -> (list, list):
    """Loads the user's JSON course file."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        course_strings = [f"{c['subject']} {c['number']}" for c in data['courses']]
        course_objects = data['courses']
        return course_strings, course_objects
    except FileNotFoundError:
        print(f"Error: Could not find file at {filepath}")
        exit(1)

def load_manual_rule_file(filepath: str) -> dict:
    """Loads a specific JSON rule file you wrote."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"\n--- WARNING ---")
        print(f"Missing manual rule file: {filepath}")
        print("This is okay, but general rules (like total credits) will be skipped.")
        return {"name": "Manual Rules (Missing)", "rules": []}

def print_requirements_summary(program_name: str, rule_data_list: list):
    """Prints a clean summary of all REQUIRED COURSES."""
    print("\n" + "="*50)
    print(f"REQUIREMENTS SUMMARY FOR: {program_name}")
    print("="*50)
    
    total_courses_found = 0

    for rule_data in rule_data_list:
        if not rule_data.get('rules'):
            continue
            
        for rule in rule_data['rules']:
            # We only care about rules that are a 'COURSE_LIST'
            if rule.get('type') == 'COURSE_LIST':
                courses = rule.get('courses', [])
                if courses:
                    total_courses_found += len(courses)
                    print(f"\n### From: {rule_data['name']} ({rule.get('description')})")
                    for i, course in enumerate(courses):
                        print(f"  - {course:<12}", end="" if (i + 1) % 4 else "\n")
                    print()
    
    if total_courses_found == 0:
        print("\nNo specific required courses were auto-scraped for this program.")
        
    print("\n" + "="*50)
    print("\nNow, please provide your list of completed courses.")

def run_audit(rules_data: dict, course_strings: list, course_objects: list):
    """The 'brain' of the CLI. Checks rules against courses."""
    print(f"\n--- AUDITING: {rules_data['name']} ---")
    
    for rule in rules_data.get('rules', []):
        rule_type = rule.get('type')
        description = rule.get('description', 'Unnamed Rule')
        
        try:
            # Check for specific required courses
            if rule_type == 'COURSE_LIST':
                missing_courses = []
                for course in rule.get('courses', []):
                    if course not in course_strings:
                        missing_courses.append(course)
                
                if not missing_courses:
                    print(f" {description} (All courses taken)")
                else:
                    print(f" {description} (Missing: {', '.join(missing_courses)})")

            # Check for total credits (from common.json)
            elif rule_type == 'TOTAL_CREDITS':
                total_user_credits = len(course_strings) * 3  # Assuming 3 credits
                if total_user_credits >= rule.get('required', 120):
                    print(f" {description} (You have {total_user_credits})")
                else:
                    print(f" {description} (You have {total_user_credits} / {rule.get('required', 120)})")
                        
            else:
                print(f" {description} (Skipped: Unknown rule type '{rule_type}')")
                
        except Exception as e:
            print(f" Error processing rule '{description}': {e}")



async def main():
    print("Welcome to the UofA Academic Progress Tracker")
    print("Starting browser to fetch live UofA Calendar...")
    print("(This may take 10-20 seconds)")
    
    all_rules_to_run = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # 1. Scrape and Parse the Menu
        main_soup = await fetch_page_soup(page, FACULTIES_URL)
        if not main_soup:
            print("Fatal: Could not load main faculty page."); await browser.close(); return

        catalog = parse_menu_from_html(main_soup)
        if not catalog:
            print("Could not parse the catalog. Exiting."); await browser.close(); return

        # 2. Load common manual rules
        common_rules = load_manual_rule_file("rules/common.json")
        all_rules_to_run.append(common_rules)
        
        # 3. Run the selection menus
        faculty_name = await questionary.select(
            "Please select your faculty:",
            choices=list(catalog.keys())
        ).ask_async()
        
        program_name = await questionary.select(
            "Please select your program:",
            choices=list(catalog[faculty_name].keys())
        ).ask_async()
        
        program_data = catalog[faculty_name][program_name]
        
        # 4. Scrape AUTO rules (courses)
        auto_courses = await scrape_required_courses(page, program_data['source_url'])
        
        # Handle Engineering Common Year
        if "Faculty of Engineering" in faculty_name and "Qualifying Year" not in program_name:
            print("Engineering program detected, adding common first-year requirements...")
            try:
                q_year_url = catalog[faculty_name]["Bachelor of Science in Engineering - Qualifying Year"]['source_url']
                q_year_courses = await scrape_required_courses(page, q_year_url)
                auto_courses.extend(q_year_courses)
            except KeyError:
                print("  -> Warning: Could not find 'Qualifying Year' to scrape common rules.")
        
        # Add the auto-scraped courses as their own rule
        auto_course_rules = {
            "name": f"{program_name} (Auto-Scraped)",
            "rules": [
                {
                    "description": "Auto-Scraped Required Courses (from calendar):",
                    "type": "COURSE_LIST",
                    "courses": sorted(list(set(auto_courses)))
                }
            ]
        }
        all_rules_to_run.append(auto_course_rules)

        # 5. --- We are done with the browser ---
        await browser.close()
    
    # 6. Print the summary
    print_requirements_summary(program_name, all_rules_to_run)
    
    # 7. Get path to user's courses
    course_file_path = await questionary.path(
        "Please enter the path to your 'my_courses.json' file:",
        default="my_courses.json",
        file_filter=lambda p: p.endswith('.json')
    ).ask_async()
    
    # 8. Load user's courses
    course_strings, course_objects = load_user_courses(course_file_path)
    
    # 9. Run the STACKED audit!
    print("\n" + "="*40)
    print("RUNNING YOUR ACADEMIC AUDIT...")
    print("="*40)
    
    for rules in all_rules_to_run:
        # We pass empty master_lists since we removed that rule type
        run_audit(rules, course_strings, course_objects, {}) 
        
    print("\n" + "="*40)
    print("AUDIT COMPLETE")
    print("="*40)


if __name__ == "__main__":
    asyncio.run(main())