# -*- coding: utf-8 -*-
from odoo import models, fields

class AppraisalEvaluationType(models.Model):
    _name = 'appraisal.evaluation.type'
    _description = 'Appraisal Evaluation Type'
    _order = 'sequence, id'
    
    name = fields.Char('Name', required=True)
    code = fields.Selection([
        ('department', 'Department'),
        ('role', 'Role'),
        ('common', 'Common')
    ], string='Code', required=True)
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)