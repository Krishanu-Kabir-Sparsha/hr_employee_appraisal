# -*- coding: utf-8 -*-
{
    'name': 'Employee Appraisal Integration',
    'version': '18.0.3.0.0',
    'category': 'Human Resources',
    'summary': 'Enhanced Employee Appraisal with OKR & 9-Box Integration, Multiple Evaluation Types',
    'description': """
        Employee Appraisal Integration
        ================================
        • Badge ID selection for quick employee lookup
        • OKR and 9-Box Template selection filtered by employee's teams
        • Multiple evaluation type selection (Department + Role + Common)
        • Auto-load criteria from selected templates
        • Editable actual values with real-time scoring
        • OCA Spreadsheet integration
        • Performance scoring and rating
        • Print appraisal reports (PDF)
        • Records visible in HR Employee's Appraisal tab
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'depends': [
        'hr',
        'oh_appraisal',
        'oh_appraisal_ext',
        'oh_9_box',
        'spreadsheet_oca',
        'survey',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/appraisal_evaluation_type_data.xml',
        'views/employee_badge_views.xml',
        'views/hr_appraisal_inherit_views.xml',
        'views/hr_employee_views.xml',
        'reports/appraisal_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}