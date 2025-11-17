# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    appraisal_ids = fields.One2many(
        'hr.employee.appraisal',
        'employee_id',
        string='Appraisals'
    )
    
    appraisal_count = fields.Integer(
        'Appraisal Count',
        compute='_compute_appraisal_count'
    )
    
    @api.depends('appraisal_ids')
    def _compute_appraisal_count(self):
        """Count appraisals"""
        for employee in self:
            employee.appraisal_count = len(employee.appraisal_ids)