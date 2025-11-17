# -*- coding: utf-8 -*-
{
    'name': 'Employee Appraisal Integration',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Simple Employee Appraisal with Template Integration',
    'description': """
        Employee Appraisal Integration
        ================================
        • Appraisal tab in Employee profile
        • Auto-detect templates from employee's team
        • Load criteria from OKR/9-Box templates
        • Select Department/Role/Common evaluation type
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'depends': [
        'hr',
        'oh_appraisal',
        'oh_appraisal_ext',
        'oh_9_box',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}