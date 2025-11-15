# main.py
import re
import os

COURSE_REGEX = r"[A-Z]{3,5}\s*\d{3}"

def parse_courses(text: str):
    raw_matches = re.findall(COURSE_REGEX, text.upper())
    cleaned = []

    for match in raw_matches:
        # Extract letters and digits properly
        letters = ''.join([c for c in match if c.isalpha()])
        digits = ''.join([c for c in match if c.isdigit()])

        cleaned.append(f"{letters} {digits}")

    return sorted(set(cleaned))


def main():
    print("=== UAlberta Degree Progress CLI ===")

    # 2. Ask for file path
    filepath = input("Enter path to your completed-courses text file: ").strip()

    # Validate file exists
    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}")
        return

    # 3. Read the file
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # 4. Parse
    courses = parse_courses(text)

    # 5. Output results
    print("\n===========================")
    print("Parsed Completed Courses:")
    print("===========================\n")

    for c in courses:
        print(f" - {c}")

    print(f"\nTotal unique courses detected: {len(courses)}")
    print("\nNext step: Match these to your degree requirements!")


if __name__ == "__main__":
    main()
