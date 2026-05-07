from fpdf import FPDF
import os

class AttendancePolicyPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(40, 48, 68)
        self.cell(0, 15, 'Organizational Attendance Policy & User Guide', ln=True, align='C')
        self.ln(5)
        self.set_draw_color(0, 122, 255)
        self.line(10, 30, 200, 30)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()} | Payroll System Documentation', align='C')

    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(0, 122, 255)
        self.cell(0, 10, title, ln=True, align='L')
        self.ln(4)

    def section_title(self, title):
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, title, ln=True, align='L')
        self.ln(2)

    def body_text(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(33, 37, 41)
        self.multi_cell(0, 6, text)
        self.ln(4)

    def add_bullet(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(33, 37, 41)
        self.cell(10, 6, chr(149), align='C')
        self.multi_cell(0, 6, text)
        self.ln(2)

def generate_policy():
    pdf = AttendancePolicyPDF()
    pdf.add_page()
    
    # 1. Introduction
    pdf.chapter_title("1. Introduction")
    pdf.body_text("The Attendance Policy is designed to ensure operational efficiency and accountability within the organization. This document outlines the technical features of our attendance management system and provides a guide for employees and administrators.")

    # 2. Key Features
    pdf.chapter_title("2. Key Features of the Attendance System")
    
    pdf.section_title("2.1 Automated Status Determination")
    pdf.body_text("The system automatically categorizes daily attendance based on login/logout timestamps and total worked hours:")
    pdf.add_bullet("Present: On-time login and completion of standard shift hours.")
    pdf.add_bullet("Late Login: Logging in after the designated shift start time.")
    pdf.add_bullet("Early Logout: Logging out before the designated shift end time.")
    pdf.add_bullet("Half Day: Working more than 1 hour but less than 4 hours, or violating both login and logout times.")
    pdf.add_bullet("Absent: Failure to login or working less than 1 hour in a day.")

    pdf.section_title("2.2 Geofencing and Location Security")
    pdf.body_text("To ensure integrity, the system utilizes geofencing technology:")
    pdf.add_bullet("GPS Capture: The system records the latitude and longitude during every login and logout event.")
    pdf.add_bullet("Geofence Verification: It automatically checks if the employee is within the sanctioned office perimeter.")
    pdf.add_bullet("Distance Tracking: The exact distance from the office location is logged for auditing purposes.")

    # 3. User Guide for Employees
    pdf.chapter_title("3. User Guide for Employees")
    
    pdf.section_title("3.1 Logging Daily Attendance")
    pdf.body_text("Employees must use the web dashboard to log their daily presence:")
    pdf.add_bullet("Login: Click the 'Check-In' button upon arrival at the office. Ensure location permissions are enabled in the browser.")
    pdf.add_bullet("Logout: Click the 'Check-Out' button before leaving. The system will calculate total worked hours for the day.")
    
    pdf.section_title("3.2 Attendance Corrections")
    pdf.body_text("If there is a discrepancy (e.g., forgot to check-in or technical issues), employees can request corrections:")
    pdf.add_bullet("Navigate to the 'Attendance Logs' section.")
    pdf.add_bullet("Select the specific date and click 'Request Correction'.")
    pdf.add_bullet("Provide the corrected time and a valid reason for the adjustment.")
    pdf.add_bullet("Requests are routed to HR/Admin for approval.")

    # 4. Administrative Controls
    pdf.chapter_title("4. Administrative Controls")
    pdf.body_text("Administrators have oversight of the organization's attendance matrix:")
    pdf.add_bullet("Verification: Admins can manually verify records that were flagged for geofence violations.")
    pdf.add_bullet("Approval Workflow: Admins review correction requests and can 'Approve' or 'Reject' with comments.")
    pdf.add_bullet("Analytics: Real-time dashboards show organizational attendance trends and LOP (Loss of Pay) data.")

    # 5. Compliance & RAG Metadata
    pdf.chapter_title("5. Compliance & Retrieval Metadata")
    pdf.body_text("This document is structured for efficient Retrieval-Augmented Generation (RAG).")
    pdf.section_title("Key Keywords:")
    pdf.body_text("Geofencing, Attendance Correction, Worked Hours, Late Login, Early Logout, Pro-rata Payroll, GPS Tracking, Half Day Policy.")

    output_path = "attendance_policy.pdf"
    pdf.output(output_path)
    return output_path

if __name__ == "__main__":
    path = generate_policy()
    print(f"PDF generated successfully at: {os.path.abspath(path)}")
