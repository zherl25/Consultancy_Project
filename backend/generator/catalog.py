"""What the questionnaire asks, and which activities switch on which documents.

Template files themselves live in data/templates (see tools/build_templates.py);
each one is tagged with a module key below, or "core" for documents every
company gets.
"""

MODULES: list[dict] = [
    {"key": "sales", "label": "Sales, quotations or contracts",
     "help": "You quote, tender or accept orders from customers."},
    {"key": "progress_claim", "label": "Progress claims",
     "help": "You bill customers in stages as project work is completed."},
    {"key": "purchasing", "label": "Purchasing from suppliers or subcontractors",
     "help": "You buy materials or services that affect what you deliver."},
    {"key": "project_control", "label": "Project management",
     "help": "You run site, installation or client projects with milestones."},
    {"key": "service_operation", "label": "Service delivery",
     "help": "You perform services for customers (on-site work, servicing, support)."},
    {"key": "design", "label": "Design and development",
     "help": "You design products or services. If not ticked, ISO 9001 clause 8.3 is stated as not applicable."},
    {"key": "production", "label": "Production or manufacturing",
     "help": "You make or assemble products."},
    {"key": "quality_control", "label": "Inspection and quality control",
     "help": "You inspect incoming material, work in progress or finished products."},
    {"key": "calibration", "label": "Measuring equipment that needs calibration",
     "help": "You use gauges, meters or test equipment whose accuracy matters."},
    {"key": "maintenance", "label": "Machinery or equipment maintenance",
     "help": "You maintain machines, vehicles or equipment (preventive and breakdown)."},
    {"key": "store", "label": "Store, warehouse or inventory",
     "help": "You keep stock of materials, spare parts or finished goods."},
    {"key": "it", "label": "IT systems",
     "help": "You run IT systems or support that your operation depends on."},
]
MODULE_KEYS = {m["key"] for m in MODULES}

# Company details. "required" fields are flagged in the documents when left blank.
FIELDS: list[dict] = [
    {"key": "company_name", "label": "Company name", "type": "text", "required": True,
     "placeholder": "e.g. Acme Engineering Sdn Bhd"},
    {"key": "address", "label": "Company address", "type": "textarea", "required": True,
     "placeholder": "Street, postcode, city, state"},
    {"key": "business_scope", "label": "Scope of business", "type": "text", "required": True,
     "placeholder": "e.g. Provision of mechanical and electrical engineering solutions",
     "help": "Appears as the scope of the quality management system."},
    {"key": "top_management_title", "label": "Title of top management", "type": "text", "required": True,
     "default": "Managing Director", "help": "Who approves documents and signs the quality policy."},
    {"key": "effective_date", "label": "Effective date of the documents", "type": "date", "required": True},
]

STANDARD_POLICY = [
    "Meeting our clients' and other stakeholders' needs and requirements as mutually agreed.",
    "Continually improving our product and service quality.",
    "Maintaining a quality culture throughout the organization.",
    "Satisfying all applicable requirements.",
    "Managing projects effectively and efficiently.",
    "Continually improving the quality management system.",
]

OBJECTIVE_COLUMNS: list[dict] = [
    {"key": "objective", "label": "Quality objective"},
    {"key": "measurement", "label": "Measurement"},
    {"key": "target", "label": "Target"},
    {"key": "plan", "label": "Plan to achieve it"},
    {"key": "responsibility", "label": "Responsibility"},
    {"key": "resources", "label": "Additional resources needed"},
]

FOLDERS = {"manual": "01 Quality Manual", "procedure": "02 Quality Procedure",
           "procedure_appendix": "02 Quality Procedure", "form": "03 Form"}

NOT_APPLICABLE_DESIGN = "8.3 Design and Development of Products and Services"


def schema() -> dict:
    return {"fields": FIELDS, "modules": MODULES, "standard_policy": STANDARD_POLICY,
            "objective_columns": OBJECTIVE_COLUMNS}
