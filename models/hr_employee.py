# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    # Link to hr.appraisal (oh_appraisal module)
    oh_appraisal_ids = fields.One2many(
        'hr.appraisal',
        'employee_id',
        string='OH Appraisals',
        help="Appraisals from OH Appraisal module"
    )
    
    oh_appraisal_count = fields.Integer(
        'OH Appraisal Count',
        compute='_compute_oh_appraisal_count'
    )
    
    # Existing fields
    appraisal_ids = fields.One2many(
        'hr.employee.appraisal',
        'employee_id',
        string='Employee Appraisals'
    )
    
    appraisal_count = fields.Integer(
        compute='_compute_appraisal_count',
        string='Appraisal Count'
    )
    
    @api.depends('oh_appraisal_ids')
    def _compute_oh_appraisal_count(self):
        for employee in self:
            employee.oh_appraisal_count = len(employee.oh_appraisal_ids)
    
    @api.depends('appraisal_ids')
    def _compute_appraisal_count(self):
        for employee in self:
            employee.appraisal_count = len(employee.appraisal_ids)