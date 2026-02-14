# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HrAppraisalOKRLine(models.Model):
    _name = 'hr.appraisal.okr.line'
    _description = 'Appraisal OKR Criteria Line'
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
    target_unit = fields.Char('Target Unit')
    
    # Actual (User Input)
    actual_value = fields.Float('Actual Value', help="Enter the actual achieved value")
    actual_unit = fields.Char('Actual Unit')
    
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
            # Weighted score = (Achievement % / 100) * Weightage
            line.weighted_score = (line.achievement_percentage / 100.0) * line.weightage
    
    @api.constrains('weightage')
    def _check_weightage(self):
        for line in self:
            if line.weightage < 0 or line.weightage > 100:
                raise ValidationError(_('Weightage must be between 0 and 100'))

    def write(self, vals):
        """Override write to sync actual_value changes to linked spreadsheet."""
        res = super().write(vals)
        if 'actual_value' in vals and not self.env.context.get('skip_spreadsheet_sync'):
            # Group by appraisal to avoid multiple regenerations
            appraisals = self.mapped('appraisal_id').filtered(
                lambda a: a.spreadsheet_id and a.criteria_loaded
            )
            for appraisal in appraisals:
                appraisal._sync_criteria_to_spreadsheet()
        return res