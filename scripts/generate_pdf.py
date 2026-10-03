import markdown
from fpdf import FPDF
import re

class TechfestPDF(FPDF):
    def header(self):
        self.image("header_banner.png", 0, 0, w=self.w)
        self.set_y(35)

    def footer(self):
        self.image("footer_banner.png", 0, self.h - 22, w=self.w)

def generate_pdf():
    with open("docs/Techfest_Proposal_Draft.md", "r") as f:
        md_text = f.read()



    html = markdown.markdown(md_text, extensions=['tables'])

    # Style tables and headers
    # Fix table borders
    html = html.replace('<table>', '<table border="1" cellpadding="1" cellspacing="0">')
    
    # Fix fpdf2 list page-breaking bug by converting lists to plain text with bullets
    html = html.replace('<ul>', '').replace('</ul>', '')
    html = html.replace('<li>', '&nbsp;&nbsp;&bull; ').replace('</li>', '<br>')
    html = html.replace('<hr />', '<br>')
    
    # Give table headers a clean grey/blue background and remove strong tags in td
    html = html.replace('<th>', '<th bgcolor="#D9EAD3">') 
    
    # Strip ALL tags inside <td> because fpdf2 is very strict
    import re
    def strip_tags_in_td(match):
        content = match.group(1)
        content = re.sub(r'<[^>]+>', '', content)
        return f"<td>{content}</td>"
    html = re.sub(r'<td[^>]*>(.*?)</td>', strip_tags_in_td, html, flags=re.DOTALL)

    html = re.sub(r'<td><b>(.*?)</b></td>', r'<td>\1</td>', html)

    # Make hyperlinks explicitly blue and underlined
    import re
    html = re.sub(r'<a href="([^"]+)">(.*?)</a>', r'<a href="\1"><font color="#0000FF"><u>\2</u></font></a>', html)

    
    pdf = TechfestPDF()
    pdf.add_font("arial", "", "/System/Library/Fonts/Supplemental/Arial.ttf")
    pdf.add_font("arial", "B", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    pdf.add_font("arial", "I", "/System/Library/Fonts/Supplemental/Arial Italic.ttf")
    
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_font("arial", size=10)
    
    try:
        pdf.write_html(html)
        pdf.output("UAV-X_CARES_Technical_Proposal.pdf")
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_pdf()
