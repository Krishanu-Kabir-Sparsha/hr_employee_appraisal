# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import base64

class AppraisalCriteriaData(models.Model):
    _name = 'appraisal.criteria.data'
    _description = 'Appraisal Criteria Data for Editing'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    appraisal_id = fields.Many2one(
        'hr.employee.appraisal',
        string='Appraisal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer('Sequence', default=10)
    
    display_name = fields.Char(
        'Name',
        compute='_compute_display_name',
        store=True
    )
    
    # Criteria Information
    objective_breakdown = fields.Char('Objective Breakdown')
    priority = fields.Char('Priority')
    metric = fields.Char('Metric')
    
    # Values
    target_value = fields.Float('Target Value', digits=(16, 2))
    actual_value = fields.Float('Actual Value', digits=(16, 2))
    # achieve = fields.Char('Achieve')
    
    # Weightage
    weightage = fields.Float('Weightage (%)', digits=(5, 2))
    
    # Team
    team_name = fields.Char('Team')
    
    # Type
    criteria_type = fields.Selection([
        ('okr_dept', 'OKR Department'),
        ('okr_role', 'OKR Role'),
        ('okr_common', 'OKR Common'),
        ('ninebox_perf_dept', '9-Box Performance Department'),
        ('ninebox_perf_role', '9-Box Performance Role'),
        ('ninebox_perf_common', '9-Box Performance Common'),
        ('ninebox_pot_dept', '9-Box Potential Department'),
        ('ninebox_pot_role', '9-Box Potential Role'),
        ('ninebox_pot_common', '9-Box Potential Common'),
    ], string='Criteria Type', required=True)
    
    # Achievement calculation
    achievement_percentage = fields.Float(
        'Achievement %',
        compute='_compute_achievement',
        store=True,
        digits=(5, 2)
    )
    
    @api.depends('objective_breakdown', 'sequence')
    def _compute_display_name(self):
        """Generate display name for better identification"""
        for record in self:
            if record.objective_breakdown:
                record.display_name = f"#{record.sequence} - {record.objective_breakdown[:50]}"
            else:
                record.display_name = f"Criteria #{record.sequence}"
    
    @api.depends('actual_value', 'target_value')
    def _compute_achievement(self):
        """Calculate achievement percentage"""
        for record in self:
            if record.target_value > 0:
                record.achievement_percentage = (record.actual_value / record.target_value) * 100
            else:
                record.achievement_percentage = 0.0
    
    @api.constrains('weightage')
    def _check_weightage(self):
        """Validate weightage"""
        for record in self:
            if record.weightage < 0 or record.weightage > 100:
                raise ValidationError(_('Weightage must be between 0 and 100'))
    
    @api.model
    def generate_spreadsheet_from_criteria(self, criteria_records, appraisal):
        """Generate spreadsheet data structure from criteria records"""
        
        # Get locale
        lang = self.env['res.lang']._lang_get(self.env.user.lang)
        locale = lang._odoo_lang_to_spreadsheet_locale()
        
        # Check if this is 9-Box with separate Performance & Potential
        is_ninebox = appraisal.template_type == 'ninebox'
        
        if is_ninebox:
            # Separate Performance and Potential criteria
            perf_criteria = criteria_records.filtered(
                lambda c: c.criteria_type in ['ninebox_perf_dept', 'ninebox_perf_role', 'ninebox_perf_common']
            )
            pot_criteria = criteria_records.filtered(
                lambda c: c.criteria_type in ['ninebox_pot_dept', 'ninebox_pot_role', 'ninebox_pot_common']
            )
            
            return self._generate_ninebox_spreadsheet(perf_criteria, pot_criteria, locale)
        else:
            # OKR - single table
            return self._generate_standard_spreadsheet(criteria_records, locale, 'OKR Criteria')

    def _generate_standard_spreadsheet(self, criteria_records, locale, sheet_name):
        """Generate standard spreadsheet with single table"""
        
        cells = {}
        headers = [
            'Seq', 'Objective Breakdown', 'Priority', 'Metric',
            'Target Value', 'Actual Value', 'Achievement %',
            # 'Achieve', 
            'Weightage %', 'Team'
        ]
        
        # Header row
        for col_idx, header in enumerate(headers):
            col_letter = self._number_to_column(col_idx)
            cells[f'{col_letter}1'] = {
                'content': header,
                'style': 1  # Header style
            }
        
        # Data rows
        for row_idx, record in enumerate(criteria_records.sorted('sequence'), start=2):
            data = [
                record.sequence,
                record.objective_breakdown or '',
                record.priority or '',
                record.metric or '',
                record.target_value,
                record.actual_value,
                record.achievement_percentage,
                # record.achieve or '',
                record.weightage,
                record.team_name or '',
            ]
            
            for col_idx, value in enumerate(data):
                col_letter = self._number_to_column(col_idx)
                cell_ref = f'{col_letter}{row_idx}'
                
                if isinstance(value, float):
                    cells[cell_ref] = {
                        'content': str(round(value, 2)),
                        'format': 1
                    }
                else:
                    cells[cell_ref] = {'content': str(value)}
        
        # Totals row
        total_row = len(criteria_records) + 2
        cells[f'A{total_row}'] = {'content': 'TOTALS:', 'style': 2}
        cells[f'E{total_row}'] = {
            'content': str(round(sum(criteria_records.mapped('target_value')), 2)),
            'style': 2
        }
        cells[f'F{total_row}'] = {
            'content': str(round(sum(criteria_records.mapped('actual_value')), 2)),
            'style': 2
        }
        cells[f'I{total_row}'] = {
            'content': str(round(sum(criteria_records.mapped('weightage')), 2)),
            'style': 2
        }
        
        return {
            'version': 16,
            'sheets': [{
                'id': 'sheet1',
                'name': sheet_name,
                'colNumber': len(headers),
                'rowNumber': total_row,
                'cells': cells,
                'merges': [],
            }],
            'styles': {
                '1': {'bold': True, 'fillColor': '#4A90E2', 'textColor': '#FFFFFF'},
                '2': {'bold': True, 'fillColor': '#E8F5E9'}
            },
            'formats': {'1': '#,##0.00'},
            'borders': {},
            'settings': {'locale': locale},
            'revisionId': 'START_REVISION',
        }

    def _generate_ninebox_spreadsheet(self, perf_criteria, pot_criteria, locale):
        """Generate 9-Box spreadsheet with TWO separate sheets for Performance & Potential"""
        
        sheets = []
        headers = [
            'Seq', 'Objective Breakdown', 'Priority', 'Metric',
            'Target Value', 'Actual Value', 'Achievement %',
            # 'Achieve', 
            'Weightage %', 'Team'
        ]
        
        # ========================================
        # SHEET 1: PERFORMANCE CRITERIA
        # ========================================
        if perf_criteria:
            perf_cells = {}
            
            # Performance Header Row (Green theme)
            for col_idx, header in enumerate(headers):
                col_letter = self._number_to_column(col_idx)
                perf_cells[f'{col_letter}1'] = {
                    'content': header,
                    'style': 3  # Performance header style (green)
                }
            
            # Performance Data Rows
            for row_idx, record in enumerate(perf_criteria.sorted('sequence'), start=2):
                data = [
                    record.sequence,
                    record.objective_breakdown or '',
                    record.priority or '',
                    record.metric or '',
                    record.target_value,
                    record.actual_value,
                    record.achievement_percentage,
                    # record.achieve or '',
                    record.weightage,
                    record.team_name or '',
                ]
                
                for col_idx, value in enumerate(data):
                    col_letter = self._number_to_column(col_idx)
                    cell_ref = f'{col_letter}{row_idx}'
                    
                    if isinstance(value, float):
                        perf_cells[cell_ref] = {
                            'content': str(round(value, 2)),
                            'format': 1
                        }
                    else:
                        perf_cells[cell_ref] = {'content': str(value)}
            
            # Performance Totals
            perf_total_row = len(perf_criteria) + 2
            perf_cells[f'A{perf_total_row}'] = {'content': 'TOTALS:', 'style': 4}
            perf_cells[f'E{perf_total_row}'] = {
                'content': str(round(sum(perf_criteria.mapped('target_value')), 2)),
                'style': 4
            }
            perf_cells[f'F{perf_total_row}'] = {
                'content': str(round(sum(perf_criteria.mapped('actual_value')), 2)),
                'style': 4
            }
            perf_cells[f'I{perf_total_row}'] = {
                'content': str(round(sum(perf_criteria.mapped('weightage')), 2)),
                'style': 4
            }
            
            sheets.append({
                'id': 'performance_sheet',
                'name': '📊 Performance Criteria',
                'colNumber': len(headers),
                'rowNumber': perf_total_row,
                'cells': perf_cells,
                'merges': [],
            })
        
        # ========================================
        # SHEET 2: POTENTIAL CRITERIA
        # ========================================
        if pot_criteria:
            pot_cells = {}
            
            # Potential Header Row (Blue theme)
            for col_idx, header in enumerate(headers):
                col_letter = self._number_to_column(col_idx)
                pot_cells[f'{col_letter}1'] = {
                    'content': header,
                    'style': 5  # Potential header style (blue)
                }
            
            # Potential Data Rows
            for row_idx, record in enumerate(pot_criteria.sorted('sequence'), start=2):
                data = [
                    record.sequence,
                    record.objective_breakdown or '',
                    record.priority or '',
                    record.metric or '',
                    record.target_value,
                    record.actual_value,
                    record.achievement_percentage,
                    # record.achieve or '',
                    record.weightage,
                    record.team_name or '',
                ]
                
                for col_idx, value in enumerate(data):
                    col_letter = self._number_to_column(col_idx)
                    cell_ref = f'{col_letter}{row_idx}'
                    
                    if isinstance(value, float):
                        pot_cells[cell_ref] = {
                            'content': str(round(value, 2)),
                            'format': 1
                        }
                    else:
                        pot_cells[cell_ref] = {'content': str(value)}
            
            # Potential Totals
            pot_total_row = len(pot_criteria) + 2
            pot_cells[f'A{pot_total_row}'] = {'content': 'TOTALS:', 'style': 6}
            pot_cells[f'E{pot_total_row}'] = {
                'content': str(round(sum(pot_criteria.mapped('target_value')), 2)),
                'style': 6
            }
            pot_cells[f'F{pot_total_row}'] = {
                'content': str(round(sum(pot_criteria.mapped('actual_value')), 2)),
                'style': 6
            }
            pot_cells[f'I{pot_total_row}'] = {
                'content': str(round(sum(pot_criteria.mapped('weightage')), 2)),
                'style': 6
            }
            
            sheets.append({
                'id': 'potential_sheet',
                'name': '🚀 Potential Criteria',
                'colNumber': len(headers),
                'rowNumber': pot_total_row,
                'cells': pot_cells,
                'merges': [],
            })
        
        return {
            'version': 16,
            'sheets': sheets,
            'styles': {
                '1': {'bold': True, 'fillColor': '#4A90E2', 'textColor': '#FFFFFF'},  # OKR header
                '2': {'bold': True, 'fillColor': '#E8F5E9'},  # OKR totals
                '3': {'bold': True, 'fillColor': '#4CAF50', 'textColor': '#FFFFFF'},  # Performance header (Green)
                '4': {'bold': True, 'fillColor': '#C8E6C9'},  # Performance totals (Light Green)
                '5': {'bold': True, 'fillColor': '#2196F3', 'textColor': '#FFFFFF'},  # Potential header (Blue)
                '6': {'bold': True, 'fillColor': '#BBDEFB'},  # Potential totals (Light Blue)
            },
            'formats': {'1': '#,##0.00'},
            'borders': {},
            'settings': {'locale': locale},
            'revisionId': 'START_REVISION',
        }
    
    def _number_to_column(self, n):
        """Convert number to Excel column letter (0=A, 1=B, ..., 25=Z, 26=AA, etc.)"""
        result = ""
        while n >= 0:
            result = chr(65 + (n % 26)) + result
            n = n // 26 - 1
        return result