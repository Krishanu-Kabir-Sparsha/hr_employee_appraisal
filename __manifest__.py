# -*- coding: utf-8 -*-
{
    'name': 'Employee Appraisal Integration',
    'version': '18.0.2.0.0',
    'category': 'Human Resources',
    'summary': 'Enhanced Employee Appraisal with OKR & 9-Box Template Integration',
    'description': """
        Employee Appraisal Integration
        ================================
        • Appraisal tab in Employee profile
        • Badge ID selection for quick employee lookup
        • OKR and 9-Box Template selection in appraisal forms
        • Auto-detect templates from employee's team
        • Load criteria from OKR/9-Box templates
        • Select Department/Role/Common evaluation type
        • Internal link buttons to navigate to templates
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'depends': [
        'hr',
        'oh_appraisal',
        'oh_appraisal_ext',
        'oh_9_box',
        'spreadsheet_oca',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/employee_badge_views.xml',
        'views/hr_appraisal_inherit_views.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}