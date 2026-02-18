import re

class MetadataExtractor:
    def __init__(self):
        self.current_chapter = None
        self.current_section = None
        self.current_subsection = None
        self.is_exercise_mode = False 

    def process_content_and_get_meta(self, content):
        if not content:
            return self._get_current_dict("")

        lines = content.split('\n')
        clean_lines = []

        for line in lines:
            stripped = line.strip()
            
            chap_match = re.match(r"^(?:##\s+)?(?:CHAPTER\s+)?(\d+)\s+([A-Z\s]{3,})", stripped, re.I)
            if chap_match:
                self.current_chapter = f"{chap_match.group(1)} {chap_match.group(2).strip()}".upper()
                self.current_section = None
                self.is_exercise_mode = False 
                continue

            sec_match = re.match(r"^(?:###\s+)?(\d+\.\d+)\.?\s+([A-Z][A-Za-z\s\-\:\,]+)", stripped)
            if sec_match:
                title = sec_match.group(2).strip()
                self.current_section = f"{sec_match.group(1)} {title}"
                if "EXERCISES" in title.upper():
                    self.is_exercise_mode = True
                else:
                    self.is_exercise_mode = False
                continue

            ex_match = re.match(r"^Exercise\s+(\d+\.\d+)\.?", stripped, re.I)
            if ex_match:
                self.current_section = f"Exercise {ex_match.group(1)}"
                return self._get_current_dict("\n".join(lines), force_new_chunk=True)

            if re.match(r"^\d+$", stripped.replace('#', '').strip()): continue
            
            clean_lines.append(line)

        return self._get_current_dict("\n".join(clean_lines).strip())

    def _get_current_dict(self, clean_text, force_new_chunk=False):
        return {
            "chapter_title": self.current_chapter,
            "section_title": self.current_section,
            "subsection_title": self.current_subsection,
            "clean_content": clean_text,
            "force_new_chunk": force_new_chunk,
            "is_exercise": "Exercise" in (self.current_section or "")
        }

    def get_references(self, text):
        return {
            "referenced_figures": list(set(re.findall(r"figure\s+(\d+\.\d+)", text, re.I))),
            "referenced_tables": list(set(re.findall(r"table\s+(\d+\.\d+)", text, re.I)))
        }