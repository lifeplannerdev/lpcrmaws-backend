from django.core.management.base import BaseCommand
from programs.models import Program, ProgramCountry, ProgramUniversity, ProgramIntake

PROGRAMS_DATA = [
    {
        "title": "AUSBILDUNG PROGRAM (Nursing / Nursing Assistant / Hotel & Gastronomy)",
        "country": "Germany",
        "university": "Recruitment partners – IAS College, Germany & Deutsche Karriere, Germany & many more",
        "intake": "Nursing & Nursing Assistant – Summer (Mar/Apr) & Winter (Sep/Oct) semester each year. Hotel & Gastronomy – September intake only",
        "course_duration": "Nursing – 3 years; Nursing Assistant – 1 or 1.5 years; Hotel & Gastronomy – 3 years",
        "qualification": "1) 12th + B2 German 2) 10th + 3-yr diploma or ITI + B2 German 3) Degree + B2 German",
        "fees_structure": [
            {"name": "Application/Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Admission Letter / On Ausbildung Contract", "amount": "4000 EUR"},
            {"name": "On issuance of Letter of Confirmation on Language from employer", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Visa Approval", "amount": "1000 EUR (if not fully B2 qualified)"},
            {"name": "Overall expense (visa charges, travel insurance, flight ticket, accommodation deposit)", "amount": "Around 6–7 Lakhs"}
        ],
        "services": [
            "Enrollment to the Admission", "Documentation for application", "Application submission",
            "Free Interview preparation", "Interview coordination", "Ausbildung contract/Offer of admission upon selection",
            "Issuance of Letter of Confirmation on Language from employer (if student lacks full B2 module or B2 certificate expired >1 yr)",
            "Visa appointment assistance & complete guidance on visa processing", "Visa documentation & orientation for visa application submission",
            "Travel medical insurance assistance (for visa)", "Accommodation arrangements assistance", "Flight ticket booking assistance",
            "Pre-departure briefing session (hybrid meeting with MD & Ausbildung recruiter)", "Airport pick-up & drop at accommodation",
            "Document German translation (if needed) & VFS date booking through agent — physical submission cost additional as per scenario"
        ]
    },
    {
        "title": "PRE-VOCATIONAL PROGRAM (PVP)",
        "country": "Germany",
        "university": "Course provided by IAS College at its campus in Schwerin, Germany",
        "intake": "Class starts once visa is approved (not intake-based)",
        "course_duration": "6 months, including B1 & B2 level training",
        "qualification": "1) 12th + B2 German 2) 10th + 3-yr diploma or ITI + B2 German 3) Degree + B2 German",
        "fees_structure": [
            {"name": "Application/Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Admission Acceptance Form (AAF)/Offer letter", "amount": "50,000 + GST = 59,000/-"},
            {"name": "Courier charge to Germany", "amount": "Max 4,500/- (per no. of documents/weight)"},
            {"name": "On Ministry Letter", "amount": "25,000 + GST = 29,500/-"},
            {"name": "Upon Visa Approval", "amount": "50,000 + GST = 59,000/-"}
        ],
        "services": [
            "Enrollment to the Admission", "Documentation for application", "Application submission",
            "Admission Acceptance Form (AAF)/Offer Letter", "Document attestation & courier assistance (for ministry letter processing)",
            "Ministry Letter", "Visa appointment assistance & complete guidance on visa processing",
            "Visa documentation & orientation for visa application submission", "Travel medical insurance assistance (for visa)",
            "Accommodation arrangements assistance", "Flight ticket booking assistance", "Pre-departure briefing session",
            "Airport pick-up & drop at accommodation"
        ]
    },
    {
        "title": "GERMAN CHANCE CARD PROGRAM (GCC Program)",
        "country": "Germany",
        "university": "Course provided by IAS College at its campus in Schwerin, Germany",
        "intake": "Class starts once visa is approved (not intake-based)",
        "course_duration": "6 months job-oriented training including B1 & B2 level German class",
        "qualification": "1) 12th + A2 German or above 2) 10th + 3-yr diploma or ITI + A2 German 3) Degree + A2 German or above 4) Master's + A2 German or above — and must qualify eligibility assessment",
        "fees_structure": [
            {"name": "Application/Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Admission Acceptance Form (AAF)/Offer letter", "amount": "50,000 + GST = 59,000/-"},
            {"name": "On Ministry Letter", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Visa Approval", "amount": "50,000 + GST = 59,000/-"}
        ],
        "services": [
            "Enrollment to the Admission", "Documentation for application", "Application submission",
            "Admission Acceptance Form (AAF)/Offer Letter", "Ministry Letter", "Visa appointment assistance & complete guidance on visa processing",
            "Visa documentation & orientation for visa application submission", "Travel medical insurance assistance (for visa)",
            "Accommodation arrangements assistance", "Flight ticket booking assistance", "Pre-departure briefing session",
            "Airport pick-up & drop at accommodation"
        ]
    },
    {
        "title": "English Study Eligibility Program (E-STEP Program)",
        "country": "Germany",
        "university": "Course provided by IAS College at its campus in Schwerin, Germany",
        "intake": "Based on the university admission cycle",
        "course_duration": "1 year",
        "qualification": "12th qualification (good to have German basics, IELTS)",
        "fees_structure": [
            {"name": "Application/Registration Fee", "amount": "20,000 + GST = 23,600/-"},
            {"name": "Documentation fee at offer letter", "amount": "50,000 + GST = 59,000/-"},
            {"name": "Service charge after visa granted", "amount": "700 EUR (to the Polish bank account)"}
        ],
        "services": []
    },
    {
        "title": "GERMANY PRIVATE UNIVERSITIES",
        "country": "Germany",
        "university": "Various",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Application/Registration Fee", "amount": "5,000 + GST = 5,900/-"},
            {"name": "APS Attestation support", "amount": "2,000/-"}
        ],
        "services": []
    },
    {
        "title": "GERMANY PUBLIC UNIVERSITIES",
        "country": "Germany",
        "university": "Various",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "35,000/-"},
            {"name": "After Offer Letter", "amount": "50,000/-"},
            {"name": "On Visa Appointment", "amount": "50,000/-"},
            {"name": "Total Service Charge", "amount": "1,35,000/-"}
        ],
        "services": []
    },
    {
        "title": "FLAG GERMAN COURSE",
        "country": "Germany",
        "university": "",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Special offer – A1–B2 course work, one-time payment", "amount": "1,06,200/-"},
            {"name": "3 installments of 38,000 (1st of every month for 3 months)", "amount": "1,12,000/- total"},
            {"name": "Monthly plan: Registration", "amount": "20,000/-, then 9,500/month for months 2–11 (10 months)"},
            {"name": "Level-based fees", "amount": "A1: 21,240/-; A2: 21,240/-; B1: 29,500/-; B2: 47,200/-"}
        ],
        "services": []
    },
    {
        "title": "POLAND PUBLIC UNIVERSITIES",
        "country": "Poland",
        "university": "Various",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Admission Letter/Offer Letter", "amount": "79,000 + GST = 93,220/-"},
            {"name": "On Visa Appointment", "amount": "700 EUR"},
            {"name": "Total Service Charge", "amount": "1,65,500/-"}
        ],
        "services": []
    },
    {
        "title": "POLAND PRIVATE UNIVERSITIES",
        "country": "Poland",
        "university": "Various",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Admission Letter/Offer Letter", "amount": "79,000 + GST = 93,220/-"},
            {"name": "On Visa Appointment", "amount": "700 EUR"},
            {"name": "Total Service Charge", "amount": "1,65,500/-"}
        ],
        "services": []
    },
    {
        "title": "CM NCU — Collegium Medicum Nicolaus Copernicus University (Medicine)",
        "country": "Poland",
        "university": "CM NCU",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "280 EUR"},
            {"name": "On Admission Letter", "amount": "800 EUR (main list) / 1,500 EUR (Poland sheet)"},
            {"name": "On Visa Appointment", "amount": "1,500 EUR"}
        ],
        "services": []
    },
    {
        "title": "UNIVERSITY OF LODZ",
        "country": "Poland",
        "university": "University of Lodz",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Offer Letter", "amount": "59,000/-"},
            {"name": "On Visa Appointment", "amount": "700 EUR"},
            {"name": "Total Service Charge", "amount": "1,65,500/-"}
        ],
        "services": []
    },
    {
        "title": "MEDICAL UNIVERSITY OF LODZ",
        "country": "Poland",
        "university": "Medical University of Lodz",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "250 EUR (main list) / 280 EUR (Poland sheet)"},
            {"name": "On Admission Letter", "amount": "800 EUR (main list) / 1,500 EUR (Poland sheet)"},
            {"name": "On Visa Appointment", "amount": "1,500 EUR"}
        ],
        "services": []
    },
    {
        "title": "ECOTUR",
        "country": "Spain",
        "university": "Ecotur",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "25,000 + GST = 29,500/-"},
            {"name": "On Offer Letter", "amount": "59,000/-"},
            {"name": "On Visa", "amount": "40,000/-"}
        ],
        "services": []
    },
    {
        "title": "BSBI SPAIN (Spain Campus)",
        "country": "Spain",
        "university": "BSBI",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "29,500/-"}
        ],
        "services": []
    },
    {
        "title": "FRANCE",
        "country": "France",
        "university": "",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [],
        "services": []
    },
    {
        "title": "MALTA (Commission-based)",
        "country": "Malta",
        "university": "",
        "intake": "September 2026 / January 2027 / April 2027 / September 2027",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "1–15 visas", "amount": "10%"},
            {"name": "15–25 visas", "amount": "15%"},
            {"name": "25–35 visas", "amount": "20%"},
            {"name": "Above 35 visas", "amount": "25%"}
        ],
        "services": []
    },
    {
        "title": "VISTULA & AVANZA",
        "country": "Malta",
        "university": "Vistula & Avanza",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "29,500/-"},
            {"name": "On Offer Letter", "amount": "59,000/-"},
            {"name": "On Visa", "amount": "40,000/-"},
            {"name": "Total Service Charge", "amount": "1,28,500/-"}
        ],
        "services": []
    },
    {
        "title": "Alexander College, Cyprus",
        "country": "Cyprus",
        "university": "Alexander College",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "29,500/-"},
            {"name": "On Offer Letter", "amount": "59,000/-"},
            {"name": "On Visa", "amount": "700 EUR"}
        ],
        "services": []
    },
    {
        "title": "University of Debrecen",
        "country": "Hungary",
        "university": "University of Debrecen",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "11,800/-"},
            {"name": "On Offer Letter", "amount": "29,500/- (non-refundable)"}
        ],
        "services": []
    },
    {
        "title": "Tio Business School",
        "country": "Netherlands",
        "university": "Tio Business School",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "11,800/-"},
            {"name": "On Offer Letter", "amount": "29,500/- (non-refundable)"}
        ],
        "services": []
    },
    {
        "title": "Danford College, Melbourne",
        "country": "Australia",
        "university": "Danford College",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "10,000/-"},
            {"name": "On Visa", "amount": "NA"}
        ],
        "services": []
    },
    {
        "title": "ITALY HOTEL MANAGEMENT BRESCIA",
        "country": "Italy",
        "university": "Hotel Management Brescia",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration Fee", "amount": "29,500/-"}
        ],
        "services": []
    },
    {
        "title": "MBBS, Moldova",
        "country": "Moldova",
        "university": "Moldova",
        "intake": "",
        "course_duration": "",
        "qualification": "",
        "fees_structure": [
            {"name": "Registration/Application Fee", "amount": "1000 EUR + GST"}
        ],
        "services": []
    }
]

class Command(BaseCommand):
    help = 'Seeds program data from Add_Program_Form_Data.md'

    def handle(self, *args, **kwargs):
        Program.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Cleared existing programs'))

        # Add predefined countries
        countries = [
            "Germany", "Poland", "Spain", "France", "Malta", "Cyprus", 
            "Hungary", "Netherlands", "Australia", "Italy", "Moldova"
        ]
        
        for c in countries:
            ProgramCountry.objects.get_or_create(name=c)
            
        for data in PROGRAMS_DATA:
            country_obj, _ = ProgramCountry.objects.get_or_create(name=data["country"]) if data["country"] else (None, False)
            uni_obj, _ = ProgramUniversity.objects.get_or_create(name=data["university"]) if data["university"] else (None, False)
            intake_obj, _ = ProgramIntake.objects.get_or_create(name=data["intake"]) if data["intake"] else (None, False)
            
            Program.objects.create(
                title=data["title"],
                country=country_obj,
                university=uni_obj,
                intake=intake_obj,
                course_duration=data["course_duration"],
                qualification=data["qualification"],
                fees_structure=data["fees_structure"],
                services=data["services"]
            )
            
        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {len(PROGRAMS_DATA)} programs.'))
