# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HrAppraisalNineboxPerformanceLine(models.Model):
    _name = 'hr.appraisal.ninebox.performance.line'
    _description = 'Appraisal 9-Box Performance Line'
    _order = 'sequence, id'

    appraisal_id = fields.Many2one('hr.appraisal', string='Appraisal', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('Sequence', default=10)
    
    # Criteria Type
    line_type = fields.Selection([
        ('department', 'Department'),
        ('role', 'Role'),
        ('common', 'Common')
    ], string='Type', required=True)
    
    # From Template
    objective_breakdown = fields.Char('Objective Breakdown', required=True)
    priority = fields.Selection([
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low')
    ], string='Priority')
    metric = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('count', 'Count (Numeric)'),
        ('rating', 'Rating (Scale)'),
        ('score', 'Score (Points)')
    ], string='Metric/Measure')
    
    # Target
    target_value = fields.Float('Target Value', required=True)
    
    # Actual (User Input)
    actual_value = fields.Float('Actual Value', help="Enter the actual achieved value")
    
    # Weightage
    weightage = fields.Float('Weightage (%)', digits=(5, 2), required=True)
    
    # Team
    team_id = fields.Many2one('oh.appraisal.team', string='Team')
    
    # Achievement Calculation
    achievement_percentage = fields.Float('Achievement %', compute='_compute_achievement', store=True, digits=(5, 2))
    weighted_score = fields.Float('Weighted Score', compute='_compute_weighted_score', store=True, digits=(5, 2))
    
    @api.depends('actual_value', 'target_value')
    def _compute_achievement(self):
        for line in self:
            if line.target_value > 0:
                line.achievement_percentage = (line.actual_value / line.target_value) * 100
            else:
                line.achievement_percentage = 0.0
    
    @api.depends('achievement_percentage', 'weightage')
    def _compute_weighted_score(self):
        for line in self:
            line.weighted_score = (line.achievement_percentage / 100.0) * line.weightage


class HrAppraisalNineboxPotentialLine(models.Model):
    _name = 'hr.appraisal.ninebox.potential.line'
    _description = 'Appraisal 9-Box Potential Line'
    _order = 'sequence, id'

    appraisal_id = fields.Many2one('hr.appraisal', string='Appraisal', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('Sequence', default=10)
    
    # Criteria Type
    line_type = fields.Selection([
        ('department', 'Department'),
        ('role', 'Role'),
        ('common', 'Common')
    ], string='Type', required=True)
    
    # From Template
    objective_breakdown = fields.Char('Objective Breakdown', required=True)
    priority = fields.Selection([
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low')
    ], string='Priority')
    metric = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('count', 'Count (Numeric)'),
        ('rating', 'Rating (Scale)'),
        ('score', 'Score (Points)')
    ], string='Metric/Measure')
    
    # Target
    target_value = fields.Float('Target Value', required=True)
    
    # Actual (User Input)
    actual_value = fields.Float('Actual Value', help="Enter the actual achieved value")
    
    # Weightage
    weightage = fields.Float('Weightage (%)', digits=(5, 2), required=True)
    
    # Team
    team_id = fields.Many2one('oh.appraisal.team', string='Team')
    
    # Achievement Calculation
    achievement_percentage = fields.Float('Achievement %', compute='_compute_achievement', store=True, digits=(5, 2))
    weighted_score = fields.Float('Weighted Score', compute='_compute_weighted_score', store=True, digits=(5, 2))
    
    @api.depends('actual_value', 'target_value')
    def _compute_achievement(self):
        for line in self:
            if line.target_value > 0:
                line.achievement_percentage = (line.actual_value / line.target_value) * 100
            else:
                line.achievement_percentage = 0.0
    
    @api.depends('achievement_percentage', 'weightage')
    def _compute_weighted_score(self):
        for line in self:
            line.weighted_score = (line.achievement_percentage / 100.0) * line.weightage