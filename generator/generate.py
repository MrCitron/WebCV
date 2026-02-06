#!/usr/bin/env python3
"""
CV Generator - Generate HTML/PDF CV from JSONResume format
Supports translation and anonymization
"""

import json
import argparse
import sys
import os
import re
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from string import Template

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Paths
SCRIPT_DIR = Path(__file__).parent

# Load .env file (with fallback if dotenv is not installed)
def load_env_file():
    """Load .env file manually if dotenv is not available"""
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_file, override=False)
        except ImportError:
            # Fallback: manual parsing
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        # Only set if not already in environment
                        if key not in os.environ:
                            os.environ[key] = value

load_env_file()
TEMPLATES_DIR = SCRIPT_DIR / "templates"
ASSETS_DIR = SCRIPT_DIR / "assets"
LOGOS_DIR = ASSETS_DIR / "logos"

# Use output/ for CI, output_local/ for local development
IS_CI = os.getenv("CI", "").lower() == "true"
OUTPUT_DIR = SCRIPT_DIR / ("output" if IS_CI else "output_local")

# Company logo mapping (local files)
COMPANY_LOGOS = {
    "SFEIR": "assets/logos/sfeir.png",
    "Mixdata": "assets/logos/mixdata.jpg",
    "Canal+": "assets/logos/canal.svg",
    "Viseo Technologies": "assets/logos/viseo.jpg",
    "Capgemini": "assets/logos/capgemini.svg",
    "Maison du Temps et de la Mobilité": "assets/logos/belfort.jpg"
}

# Company colors
COMPANY_COLORS = {
    "SFEIR": "c-sf",
    "Mixdata": "c-mx",
    "Canal+": "c-ca",
    "Viseo Technologies": "c-vi",
    "Capgemini": "c-cg",
    "Maison du Temps et de la Mobilité": "c-ot"
}

# Client anonymization rules (applied in order)
# Format: (pattern, replacement, description)
ANONYMIZATION_RULES = [
    # Specific companies with domains
    (r'\bVoyages-SNCF\.com\b', 'Client Transports', 'Voyages-SNCF.com'),
    (r'\bButConforama\b', 'Client Distribution', 'ButConforama'),

    # Beauty Tech, Group patterns
    (r'\bLVMH\s+Beauty\s+Tech\b', 'Client Luxe', 'LVMH Beauty Tech'),
    (r'\bLVMH\b', 'Client Luxe', 'LVMH'),
    (r"\bGroupe\s+Caisse\s+d['']Epargne\b", 'Client Banque', 'Groupe Caisse d\'Epargne'),
    (r'\bGroupe\s+(\w+)\b', r'Client \1', 'Groupe XXX'),

    # Specific companies
    (r'\bGroupama\b', 'Client Assurances', 'Groupama'),
    (r'\bNatixis\b', 'Client Banque', 'Natixis'),
    (r'\bGenerali\b', 'Client Assurances', 'Generali'),
    (r'\bSociété\s+Générale\b', 'Client Banque', 'Société Générale'),
    (r'\bGE\s+Money\s+Bank\b', 'Client Banque', 'GE Money Bank'),
    (r"\bCaisse\s+d['']Epargne\s+Financement\b", 'Client Banque', 'Caisse d\'Epargne Financement'),
    (r"\bCaisse\s+d['']Epargne\b", 'Client Banque', 'Caisse d\'Epargne'),

    # Mission patterns - must be after specific replacements
    (r'\bMission\s+([A-Z][^\)]+)\b', r'Mission \1', 'Keep Mission prefix'),
]

# UI Labels and Translations
LABELS = {
    "fr": {
        "summary": "Parcours professionnel — Synthèse",
        "detail": "Parcours professionnel — Détail",
        "tldr": "TL;DR",
        "contact": "Contact",
        "education": "Formation",
        "certificates": "Certifications",
        "languages": "Langues",
        "skills": "Compétences",
        "interests": "Loisirs & Intérêts",
        "present": "Présent",
        "months": "mois",
        "year": "an",
        "years": "ans",
        "page": "Page",
        "suite": " (suite)",
        "months_list": ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Août", "Sep", "Oct", "Nov", "Déc"]
    },
    "en": {
        "summary": "Professional Experience — Summary",
        "detail": "Professional Experience — Detail",
        "tldr": "TL;DR",
        "contact": "Contact",
        "education": "Education",
        "certificates": "Certifications",
        "languages": "Languages",
        "skills": "Skills",
        "interests": "Interests",
        "present": "Present",
        "months": "months",
        "year": "year",
        "years": "years",
        "page": "Page",
        "suite": " (continued)",
        "months_list": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    }
}


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string in format YYYY-MM"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m")
    except ValueError:
        return None


def format_date(date_str: str, lang: str = "fr") -> str:
    """Format date for display"""
    if not date_str:
        return LABELS[lang]["present"]

    dt = parse_date(date_str)
    if not dt:
        return date_str

    months = LABELS[lang]["months_list"]
    return f"{months[dt.month - 1]} {dt.year}"


def calculate_duration(start: str, end: str, lang: str = "fr") -> str:
    """Calculate duration between two dates"""
    start_dt = parse_date(start)
    end_dt = parse_date(end) if end else datetime.now()

    if not start_dt:
        return ""

    months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
    years = months // 12
    remaining_months = months % 12

    lbl = LABELS[lang]

    if years == 0:
        return f"{remaining_months} {lbl['months']}"
    elif remaining_months == 0:
        return f"{years} {lbl['year'] if years == 1 else lbl['years']}"
    else:
        return f"{years} {lbl['year'] if years == 1 else lbl['years']} {remaining_months} {lbl['months']}"


def anonymize_text(text: str) -> str:
    """Anonymize client names in text using rules"""
    result = text
    for pattern, replacement, desc in ANONYMIZATION_RULES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def get_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_company_name(work_entry: Dict) -> str:
    """Extract main company name from work entry"""
    name = work_entry.get("name", "")
    # Remove parentheses content
    main_name = re.sub(r'\s*\([^)]*\)', '', name).strip()
    return main_name


def get_company_logo(company_name: str) -> str:
    """Get company logo path (relative)"""
    logo_path = COMPANY_LOGOS.get(company_name, "")
    if logo_path:
        # Check if running in generator/output context or web root
        # If generating HTML in output/, we need to go up one level to reach assets/
        return f"../{logo_path}"
    return ""


def get_company_color(company_name: str) -> str:
    """Get company color class"""
    return COMPANY_COLORS.get(company_name, "c-sf")


def group_experiences_by_company(work_list: List[Dict]) -> Dict[str, List[Dict]]:
    """Group work experiences by main company"""
    grouped = {}
    for work in work_list:
        company = get_company_name(work)
        if company not in grouped:
            grouped[company] = []
        grouped[company].append(work)
    return grouped


def translate_resume(resume_data: Dict, api_key: str, model: str = None) -> Dict:
    """Translate resume to English using Gemini API"""
    if not GEMINI_AVAILABLE:
        print("Error: google-genai package not installed. Install with: pip install google-genai")
        sys.exit(1)

    # Use specified model or default
    if model is None:
        model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    print(f"Using model: {model}")

    client = genai.Client(api_key=api_key)

    resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)

    prompt = f"""Translate this French resume to English. Keep the exact same JSON structure.
Translate all text fields including basics, work experiences, education, certificates, skills, etc.
Translate the 'name' field in 'skills' (e.g. 'Langages' -> 'Languages', 'Domaines métiers' -> 'Business Domains', 'Outils' -> 'Tools'), but keep the 'keywords' as they are (technical terms).

Special instructions for Education translation:
- Translate "DUT" as "Two-year University Technology Degree".
- Translate "Ingénieur" as "Master's Degree".
- Translate "Génie Informatique" as "Computer Science".

Keep technical terms, tool names, and company names as they are in descriptions.
Keep dates in the same format.

Here's the resume in JSON format:

{resume_json}

Return ONLY the translated JSON, without any explanation or markdown formatting."""

    response = client.models.generate_content(
        model=model,
        contents=prompt
    )
    response_text = response.text

    # Remove markdown code blocks if present
    response_text = re.sub(r'^```json\s*', '', response_text)
    response_text = re.sub(r'\s*```$', '', response_text)

    return json.loads(response_text)


def render_sidebar(basics: Dict, skills: List[Dict], education: List[Dict],
                   certificates: List[Dict], languages: List[Dict],
                   interests: List[Dict], anonymize: bool = False, lang: str = "fr") -> str:
    """Render sidebar HTML"""
    lbl = LABELS[lang]

    # Skills
    skills_section = ""
    if skills:
        skills_html = ""
        for skill in skills:
            keywords = ", ".join(skill.get("keywords", []))
            skills_html += f'''    <div class="sg">
      <div class="sg-n">{skill["name"]}</div>
      <div class="sg-k">{keywords}</div>
    </div>\n'''
        skills_section = f'''  <hr>
  <div>
    <div class="st">{lbl["skills"]}</div>
{skills_html}  </div>'''

    # Certifications
    certs_section = ""
    if certificates:
        certs_html = ""
        for cert in certificates:
            date = cert.get("date", "")
            year = date.split("-")[0] if date else ""
            certs_html += f'''    <div class="it">{cert["name"]} <span class="it-s">{year}</span></div>\n'''
        certs_section = f'''  <hr>
  <div>
    <div class="st">{lbl["certificates"]}</div>
{certs_html}  </div>'''

    # Languages
    langs_section = ""
    if languages:
        langs_html = ""
        for language in languages:
            langs_html += f'''    <div class="it">{language["language"]} · {language["fluency"]}</div>\n'''
        langs_section = f'''  <hr>
  <div>
    <div class="st">{lbl["languages"]}</div>
{langs_html}  </div>'''

    # Interests
    interests_section = ""
    if interests:
        interests_html = ""
        for interest in interests:
            keywords = ", ".join(interest.get("keywords", []))
            interests_html += f'''  <div>
    <div class="st">{interest["name"]}</div>
    <div class="it">{keywords}</div>
  </div>\n'''
        interests_section = f'''  <hr>
{interests_html}'''

    # Education
    edu_section = ""
    if education:
        edu_html = ""
        for edu in education:
            study_type = edu.get("studyType", "")
            area = edu.get("area", "")
            
            if study_type and area:
                sep = " en " if lang == "fr" else " in "
                degree = f"{study_type}{sep}{area}"
            else:
                degree = study_type or area
                
            edu_html += f'''    <div class="it"><b>{degree}</b><br><span class="it-s">{edu.get("institution", "")} · {edu.get("startDate", "")}–{edu.get("endDate", "")}</span></div>\n'''
        edu_section = f'''  <hr>
  <div>
    <div class="st">{lbl["education"]}</div>
{edu_html}  </div>'''

    # Contact
    contact_items = []
    if not anonymize and basics.get("phone"):
        contact_items.append(f'      <span>{basics["phone"]}</span>')
    if not anonymize and basics.get("email"):
        contact_items.append(f'      <span>{basics["email"]}</span>')
    if basics.get("url"):
        url = basics["url"].replace("https://", "").replace("http://", "")
        contact_items.append(f'      <a>{url}</a>')
    if basics.get("profiles"):
        for profile in basics["profiles"]:
            if profile.get("network") == "LinkedIn":
                username = profile.get("username", "")
                contact_items.append(f'      <a>linkedin.com/in/{username}</a>')
    if basics.get("location", {}).get("city"):
        contact_items.append(f'      <span>{basics["location"]["city"]}, France</span>')

    contact_html = "\n".join(contact_items)

    sidebar = f'''<aside class="sb">
  <img src="{basics.get('image', '')}" alt="{basics.get('name', '')}" class="photo">
  <div>
    <h1>{basics.get('name', '').replace(' ', '<br>')}</h1>
    <div class="sub">{basics.get('label', '').replace(' / ', '<br>')}</div>
  </div>
  <hr>
  <div>
    <div class="st">{lbl["contact"]}</div>
    <div class="ct">
{contact_html}
    </div>
  </div>
{skills_section}
{edu_section}
{certs_section}
{langs_section}
{interests_section}</aside>'''

    return sidebar


def render_page_1(resume_data: Dict, anonymize: bool = False, lang: str = "fr") -> str:
    """Render page 1 with company summaries"""
    basics = resume_data.get("basics", {})
    work = resume_data.get("work", [])
    skills = resume_data.get("skills", [])
    education = resume_data.get("education", [])
    certificates = resume_data.get("certificates", [])
    languages = resume_data.get("languages", [])
    interests = resume_data.get("interests", [])

    lbl = LABELS[lang]

    sidebar = render_sidebar(basics, skills, education, certificates, languages, interests, anonymize, lang)

    # Group experiences by company
    grouped_work = group_experiences_by_company(work)

    # Generate company summaries
    company_summaries_html = ""
    for company, experiences in grouped_work.items():
        all_starts = [exp["startDate"] for exp in experiences if exp.get("startDate")]
        all_ends = [exp["endDate"] for exp in experiences if exp.get("endDate")]

        earliest_start = min(all_starts) if all_starts else ""
        latest_end = max(all_ends) if all_ends else ""

        roles = [exp["position"].split("(")[0].strip() for exp in experiences]
        roles_str = " • ".join(list(dict.fromkeys(roles)))

        descriptions = []
        for exp in experiences:
            if exp.get("summary"):
                descriptions.append(exp["summary"])
            highlights = exp.get("highlights", [])
            non_env_highlights = [h for h in highlights if not h.startswith("Environnement:")]
            if non_env_highlights:
                descriptions.extend(non_env_highlights[:2])

        description = "<br><br>".join(descriptions[:3])

        if anonymize:
            roles_str = anonymize_text(roles_str)
            description = anonymize_text(description)

        logo = get_company_logo(company)
        color = get_company_color(company)
        duration = calculate_duration(earliest_start, latest_end or "", lang)

        company_summaries_html += f'''  <!-- {company} -->
  <div class="company-sum {color}">
    <div class="company-sum-logo">
      <img src="{logo}" alt="{company}">
    </div>
    <div class="company-sum-left">
      <div class="company-sum-name">{company}</div>
      <div class="company-sum-period">{format_date(earliest_start, lang)} – {format_date(latest_end, lang)}</div>
      <div class="company-sum-dur">{duration}</div>
    </div>
    <div class="company-sum-right">
      <div class="company-sum-roles">{roles_str}</div>
      <div class="company-sum-desc">
        {description}
      </div>
    </div>
  </div>

'''

    summary = basics.get('summary', '').replace('. ', '.<br><br>')

    page_1 = f'''<!-- ========== PAGE 1 ========== -->
<div class="page">

{sidebar}

<!-- MAIN PAGE 1 -->
<main class="mn">

  <!-- TL;DR -->
  <div class="tldr">
    <div class="tldr-title">{lbl["tldr"]}</div>
    <div class="tldr-text">
      {summary}
    </div>
  </div>

  <div class="sec-title">{lbl["summary"]}</div>

{company_summaries_html}
</main>

<div class="page-num">{lbl["page"]} 1</div>

</div>
'''
    return page_1


def split_experiences_into_pages(grouped_work: Dict, anonymize: bool = False, lang: str = "fr") -> List[Tuple[List[str], List[str]]]:
    """Split experiences into multiple pages (2 columns per page)
    Returns list of (col1_experiences, col2_experiences) tuples
    """
    # Estimate height for each experience group (rough estimation)
    # A typical experience takes about 30-40mm, let's use 35mm average
    # Available height per column: ~260mm (297mm - margins - title)
    MAX_HEIGHT_PER_COL = 255  # mm
    AVG_EXP_HEIGHT = 35  # mm per experience

    pages = []
    col1 = []
    col2 = []
    col1_height = 0
    col2_height = 0

    all_exp_groups = []
    for company, experiences in grouped_work.items():
        color = get_company_color(company)
        exp_group_html = render_experience_group(company, experiences, color, anonymize, lang)
        # Estimate height based on number of experiences
        estimated_height = len(experiences) * AVG_EXP_HEIGHT
        all_exp_groups.append((exp_group_html, estimated_height))

    for exp_html, height in all_exp_groups:
        # Try to balance columns
        if col1_height <= col2_height:
            if col1_height + height <= MAX_HEIGHT_PER_COL:
                col1.append(exp_html)
                col1_height += height
            else:
                # Start new page
                pages.append((col1, col2))
                col1 = [exp_html]
                col2 = []
                col1_height = height
                col2_height = 0
        else:
            if col2_height + height <= MAX_HEIGHT_PER_COL:
                col2.append(exp_html)
                col2_height += height
            else:
                # Start new page
                pages.append((col1, col2))
                col1 = [exp_html]
                col2 = []
                col1_height = height
                col2_height = 0

    # Add last page if not empty
    if col1 or col2:
        pages.append((col1, col2))

    return pages


def render_experience_group(company: str, experiences: List[Dict], color: str,
                            anonymize: bool = False, lang: str = "fr") -> str:
    """Render a group of experiences for one company"""
    exp_group_html = f'''      <!-- {company} -->
      <div class="exp-grp">
        <div class="exp-grp-title">{company}</div>

'''

    for exp in experiences:
        # Extract mission from name if present
        mission = ""
        if "(" in exp["name"]:
            mission_match = re.search(r'\(([^)]+)\)', exp["name"])
            if mission_match:
                mission = mission_match.group(1)
        elif "Mission" in exp["position"]:
            mission_match = re.search(r'\(([^)]+)\)', exp["position"])
            if mission_match:
                mission = mission_match.group(1)

        position = exp["position"].split("(")[0].strip()
        summary = exp.get("summary", "")

        if anonymize:
            mission = anonymize_text(mission)
            position = anonymize_text(position)
            summary = anonymize_text(summary)

        highlights = exp.get("highlights", [])
        highlights_html = ""
        for highlight in highlights:
            if anonymize:
                highlight = anonymize_text(highlight)

            if highlight.startswith("Environnement:"):
                env_text = highlight.replace("Environnement:", "").strip()
                highlights_html += f'''            <li class="exp-env">{env_text}</li>\n'''
            else:
                highlights_html += f'''            <li>{highlight}</li>\n'''

        duration = calculate_duration(exp["startDate"], exp["endDate"], lang)

        mission_html = f'<div class="exp-mi">{mission}</div>' if mission else ""

        exp_group_html += f'''        <div class="exp {color}">
          <div class="exp-co">{company}</div>
          {mission_html}
          <div class="exp-ro">{position}</div>
          <div class="exp-dt">{format_date(exp["startDate"], lang)} – {format_date(exp["endDate"], lang)} <span class="exp-dur">{duration}</span></div>
          <ul class="exp-hl">
{highlights_html}          </ul>
        </div>

'''

    exp_group_html += "      </div>\n\n"
    return exp_group_html


def render_detail_pages(resume_data: Dict, anonymize: bool = False, lang: str = "fr") -> str:
    """Render detail pages (page 2+) with experiences"""
    basics = resume_data.get("basics", {})
    work = resume_data.get("work", [])
    skills = resume_data.get("skills", [])
    education = resume_data.get("education", [])
    certificates = resume_data.get("certificates", [])
    languages = resume_data.get("languages", [])
    interests = resume_data.get("interests", [])

    lbl = LABELS[lang]

    sidebar = render_sidebar(basics, skills, education, certificates, languages, interests, anonymize, lang)

    grouped_work = group_experiences_by_company(work)
    pages_data = split_experiences_into_pages(grouped_work, anonymize, lang)

    pages_html = ""
    for page_num, (col1_exps, col2_exps) in enumerate(pages_data, start=2):
        col1_html = "".join(col1_exps)
        col2_html = "".join(col2_exps)

        page_html = f'''<!-- ========== PAGE {page_num} ========== -->
<div class="page">

{sidebar}

<!-- MAIN PAGE {page_num} -->
<main class="mn">

  <div class="sec-title">{lbl["detail"]}{lbl["suite"] if page_num > 2 else ''}</div>

  <div class="exp-cols">
    <div class="exp-col">

{col1_html}    </div>

    <div class="exp-col">

{col2_html}    </div>
  </div>

</main>

<div class="page-num">{lbl["page"]} {page_num}</div>

</div>

'''
        pages_html += page_html

    return pages_html


def generate_html(resume_data: Dict, anonymize: bool = False, lang: str = "fr") -> str:
    """Generate complete HTML from resume data"""

    # Anonymize work entries if requested
    if anonymize:
        for work_entry in resume_data.get("work", []):
            work_entry["name"] = anonymize_text(work_entry["name"])
            work_entry["position"] = anonymize_text(work_entry["position"])
            work_entry["summary"] = anonymize_text(work_entry.get("summary", ""))
            work_entry["highlights"] = [anonymize_text(h) for h in work_entry.get("highlights", [])]

    # Generate pages
    page_1 = render_page_1(resume_data, anonymize, lang)
    detail_pages = render_detail_pages(resume_data, anonymize, lang)

    # Load template
    template_file = TEMPLATES_DIR / "cv_template.html"
    with open(template_file, 'r', encoding='utf-8') as f:
        template_content = f.read()

    # Use simple string replacement for template
    html = template_content.replace('{{ lang }}', lang)
    html = html.replace('{{ name }}', resume_data.get("basics", {}).get("name", ""))
    html = html.replace('{{ content }}', page_1 + "\n" + detail_pages)

    return html


def generate_pdf(html_file: Path, pdf_file: Path) -> bool:
    """Generate PDF from HTML using wkhtmltopdf or weasyprint"""

    # Try wkhtmltopdf first
    if subprocess.run(['which', 'wkhtmltopdf'], capture_output=True).returncode == 0:
        cmd = [
            'wkhtmltopdf',
            '--page-size', 'A4',
            '--orientation', 'Portrait',
            '--margin-top', '0',
            '--margin-bottom', '0',
            '--margin-left', '0',
            '--margin-right', '0',
            '--enable-local-file-access',
            str(html_file),
            str(pdf_file)
        ]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

    # Try weasyprint
    try:
        import weasyprint
        html_content = html_file.read_text(encoding='utf-8')
        doc = weasyprint.HTML(string=html_content, base_url=str(html_file.parent))
        doc.write_pdf(str(pdf_file))
        return True
    except ImportError:
        print("Warning: Neither wkhtmltopdf nor weasyprint available for PDF generation")
        print("Install with: pip install weasyprint")
        print("Or install wkhtmltopdf from https://wkhtmltopdf.org/")
        return False
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML/PDF CV from JSONResume format",
        epilog="Resume format: https://jsonresume.org/"
    )
    parser.add_argument("input", help="Input JSON resume file (e.g., resume.json)")
    parser.add_argument("-o", "--output", help="Output file (default: output/resume-{lang}.html)")
    parser.add_argument("-t", "--translate", action="store_true", help="Translate to English using Claude API")
    parser.add_argument("-a", "--anonymize", action="store_true", help="Anonymize CV (remove contact info and client names)")
    parser.add_argument("-p", "--pdf", action="store_true", help="Also generate PDF version")
    parser.add_argument("--api-key", help="Gemini API key for translation (or set GEMINI_API_KEY env var)")
    parser.add_argument("--model", help="Gemini model to use (default: gemini-flash-lite-latest, or set GEMINI_MODEL env var)")

    args = parser.parse_args()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read input JSON
    input_file = Path(args.input)
    if not input_file.exists():
        # Try relative to script dir
        input_file = SCRIPT_DIR.parent / args.input

    if not input_file.exists():
        print(f"Error: File '{args.input}' not found")
        sys.exit(1)

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            resume_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.input}': {e}")
        sys.exit(1)

    lang = "fr"

    # Translate if requested
    if args.translate:
        api_key = args.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("Error: API key required for translation. Use --api-key or set GEMINI_API_KEY env var")
            sys.exit(1)

        model = args.model or os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        input_hash = get_file_hash(input_file)
        
        # Cache file path: resume.en.json (next to input)
        cache_file = input_file.parent / f"{input_file.stem}.en.json"
        hash_file = cache_file.with_suffix(".hash")
        
        cache_valid = False
        if cache_file.exists() and hash_file.exists():
            with open(hash_file, "r") as f:
                cached_data = f.read().strip()
                # Cache is valid if hash and model match
                if cached_data == f"{input_hash}:{model}":
                    cache_valid = True
        
        if cache_valid:
            print(f"Using cached translation from {cache_file}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                resume_data = json.load(f)
        else:
            print(f"Translating resume to English using {model}...")
            resume_data = translate_resume(resume_data, api_key, model)
            
            # Save to cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(resume_data, f, ensure_ascii=False, indent=2)
            with open(hash_file, 'w') as f:
                f.write(f"{input_hash}:{model}")
            print("✓ Translation complete and cached!")

        lang = "en"

    # Generate HTML
    print("Generating HTML...")
    html = generate_html(resume_data, anonymize=args.anonymize, lang=lang)

    # Determine output filename
    if args.output:
        output_file = Path(args.output)
    else:
        # In CI, don't add -anonymous suffix (always anonymized anyway)
        # In local, add suffix to distinguish versions
        suffix = "" if IS_CI else ("-anonymous" if args.anonymize else "")
        output_file = OUTPUT_DIR / f"resume-{lang}{suffix}.html"

    # Write HTML output
    output_file.write_text(html, encoding='utf-8')
    print(f"✓ HTML generated: {output_file}")

    if args.anonymize:
        print("  Note: CV has been anonymized (contact info removed, client names replaced)")

    # Generate PDF if requested
    if args.pdf:
        pdf_file = output_file.with_suffix('.pdf')
        print("Generating PDF...")
        if generate_pdf(output_file, pdf_file):
            print(f"✓ PDF generated: {pdf_file}")
        else:
            print("✗ PDF generation failed")
            sys.exit(1)

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
