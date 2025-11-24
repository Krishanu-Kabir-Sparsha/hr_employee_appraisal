# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json
import base64

_logger = logging.getLogger(__name__)

class HrEmployeeAppraisal(models.Model):
    _name = 'hr.employee.appraisal'
    _description = 'Employee Appraisal'
    _order = 'create_date desc'

    # ============ BASIC INFO ============
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    name = fields.Char(
        string='Appraisal Reference',
        compute='_compute_name',
        store=True
    )
    
    # ============ AUTO-DETECTED FIELDS ============
    appraisal_team_id = fields.Many2one(
        'oh.appraisal.team',
        string='Team',
        compute='_compute_team_and_templates',
        store=True,
        readonly=True
    )
    
    template_type = fields.Selection([
        ('okr', 'OKR Template'),
        ('ninebox', '9-Box Grid Template')
    ], string='Template Type', compute='_compute_team_and_templates', store=True, readonly=True)
    
    okr_template_id = fields.Many2one(
        'oh.appraisal.okr.template',
        string='OKR Template',
        compute='_compute_team_and_templates',
        store=True,
        readonly=True
    )
    
    ninebox_template_id = fields.Many2one(
        'oh.appraisal.ninebox.template',
        string='9-Box Template',
        compute='_compute_team_and_templates',
        store=True,
        readonly=True
    )
    
    # ============ USER SELECTION ============
    evaluation_type = fields.Selection([
        ('department', 'Department Criteria'),
        ('role', 'Role Criteria'),
        ('common', 'Common Criteria')
    ], string='Evaluation Type', required=True)
    
    # ============ CRITERIA DATA ============
    criteria_data = fields.Html(
        string='Evaluation Criteria',
        compute='_compute_criteria_data',
        sanitize=False
    )

    # ============ SPREADSHEET INTEGRATION ============
    criteria_data_ids = fields.One2many(
        'appraisal.criteria.data',
        'appraisal_id',
        string='Criteria Data for Spreadsheet'
    )
    
    criteria_loaded = fields.Boolean(
        'Criteria Loaded',
        default=False,
        help="Indicates if criteria data has been loaded to spreadsheet"
    )

    spreadsheet_document_id = fields.Many2one(
        'spreadsheet.spreadsheet',
        string='Spreadsheet Document',
        help="Linked spreadsheet document for this appraisal"
    )
    
    spreadsheet_name = fields.Char(
        'Spreadsheet Name',
        compute='_compute_spreadsheet_name',
        store=True
    )
    
    @api.depends('employee_id.name', 'evaluation_type', 'template_type', 'create_date')
    def _compute_spreadsheet_name(self):
        """Generate unique spreadsheet name"""
        for record in self:
            if record.employee_id and record.evaluation_type:
                employee_name = record.employee_id.name
                eval_type_label = dict(record._fields['evaluation_type'].selection).get(
                    record.evaluation_type, 'Evaluation'
                )
                template_type_label = dict(record._fields['template_type'].selection).get(
                    record.template_type, ''
                )
                date_str = fields.Datetime.now().strftime('%Y-%m-%d %H:%M')
                
                # Format: "John Doe - Department Criteria - OKR - 2025-11-18 00:04"
                parts = [employee_name, eval_type_label]
                if template_type_label:
                    parts.append(template_type_label)
                parts.append(f"({date_str})")
                
                record.spreadsheet_name = ' - '.join(parts)
            else:
                record.spreadsheet_name = "Appraisal Criteria"

    total_criteria_weightage = fields.Float(
        'Total Weightage',
        compute='_compute_total_criteria_weightage',
        digits=(5, 2)
    )
    
    criteria_data_count = fields.Integer(
        'Criteria Count',
        compute='_compute_criteria_data_count'
    )
    
    @api.depends('criteria_data_ids.weightage')
    def _compute_total_criteria_weightage(self):
        """Calculate total weightage from loaded criteria"""
        for record in self:
            record.total_criteria_weightage = sum(record.criteria_data_ids.mapped('weightage'))
    
    @api.depends('criteria_data_ids')
    def _compute_criteria_data_count(self):
        """Count loaded criteria"""
        for record in self:
            record.criteria_data_count = len(record.criteria_data_ids)
    
    # ============ COMPUTE METHODS ============
    @api.depends('employee_id')
    def _compute_name(self):
        """Generate appraisal reference name"""
        for record in self:
            if record.employee_id:
                record.name = f"Appraisal - {record.employee_id.name}"
            else:
                record.name = "New Appraisal"
    
    @api.depends('employee_id', 'employee_id.department_id')
    def _compute_team_and_templates(self):
        """Auto-detect team and templates based on employee"""
        for record in self:
            # ✅ FIX: Check if record is saved (has real ID)
            if not record.employee_id or not record.employee_id.id or isinstance(record.employee_id.id, models.NewId):
                record.appraisal_team_id = False
                record.template_type = False
                record.okr_template_id = False
                record.ninebox_template_id = False
                continue
            
            employee = record.employee_id
            
            # ✅ FIX: Only execute SQL if employee has real ID
            if not isinstance(employee.id, int):
                record.appraisal_team_id = False
                record.template_type = False
                record.okr_template_id = False
                record.ninebox_template_id = False
                continue
            
            # Get employee's teams
            self.env.cr.execute("""
                SELECT team_id 
                FROM oh_appraisal_team_employee_rel 
                WHERE employee_id = %s
            """, (employee.id,))
            
            team_ids = [row[0] for row in self.env.cr.fetchall()]
            
            if not team_ids:
                record.appraisal_team_id = False
                record.template_type = False
                record.okr_template_id = False
                record.ninebox_template_id = False
                _logger.info(f"No teams found for employee {employee.name}")
                continue
            
            # Get teams in employee's department
            teams = self.env['oh.appraisal.team'].browse(team_ids)
            dept_team = teams.filtered(
                lambda t: t.department_id == employee.department_id
            )[:1]  # Take first match
            
            if not dept_team:
                record.appraisal_team_id = False
                record.template_type = False
                record.okr_template_id = False
                record.ninebox_template_id = False
                continue
            
            record.appraisal_team_id = dept_team
            
            # Check for OKR template
            okr_template = self.env['oh.appraisal.okr.template'].search([
                ('department_id', '=', employee.department_id.id),
                ('active', '=', True),
                ('weightage_ids.team_id', '=', dept_team.id)
            ], limit=1)
            
            if okr_template:
                record.template_type = 'okr'
                record.okr_template_id = okr_template
                record.ninebox_template_id = False
                continue
            
            # Check for 9-Box template
            ninebox_template = self.env['oh.appraisal.ninebox.template'].search([
                ('department_id', '=', employee.department_id.id),
                ('active', '=', True),
                '|',
                ('performance_weightage_ids.team_id', '=', dept_team.id),
                ('potential_weightage_ids.team_id', '=', dept_team.id)
            ], limit=1)
            
            if ninebox_template:
                record.template_type = 'ninebox'
                record.ninebox_template_id = ninebox_template
                record.okr_template_id = False
            else:
                record.template_type = False
                record.okr_template_id = False
                record.ninebox_template_id = False
    
    @api.depends('evaluation_type', 'template_type', 'okr_template_id', 'ninebox_template_id', 'appraisal_team_id')
    def _compute_criteria_data(self):
        """Load and display criteria based on evaluation type"""
        for record in self:
            if not record.evaluation_type or not record.template_type:
                record.criteria_data = '<p class="text-muted">Please select an evaluation type.</p>'
                continue
            
            if record.template_type == 'okr':
                record.criteria_data = record._generate_okr_criteria_html()
            elif record.template_type == 'ninebox':
                record.criteria_data = record._generate_ninebox_criteria_html()
            else:
                record.criteria_data = '<p class="text-muted">No template found.</p>'

    
    def action_load_to_spreadsheet(self):
        """Load criteria data and automatically create spreadsheet"""
        self.ensure_one()
        
        if not self.evaluation_type or not self.template_type:
            raise UserError(_('Please select an evaluation type first.'))
        
        # Clear existing data
        self.criteria_data_ids.unlink()
        
        # Delete old spreadsheet if exists
        if self.spreadsheet_document_id:
            self.spreadsheet_document_id.unlink()
        
        criteria_list = []
        
        if self.template_type == 'okr':
            criteria_list = self._load_okr_to_spreadsheet()
        elif self.template_type == 'ninebox':
            criteria_list = self._load_ninebox_to_spreadsheet()
        
        if not criteria_list:
            raise UserError(_('No criteria found to load.'))
        
        # Create criteria records
        created_criteria = self.env['appraisal.criteria.data'].create(criteria_list)
        self.criteria_loaded = True
        
        # Generate spreadsheet name
        timestamp = fields.Datetime.now().strftime('%Y-%m-%d %H:%M')
        employee_name = self.employee_id.name
        eval_type = dict(self._fields['evaluation_type'].selection).get(
            self.evaluation_type, 'Evaluation'
        )
        spreadsheet_name = f"{employee_name} - {eval_type} Appraisal ({timestamp})"
        
        # Generate spreadsheet data
        spreadsheet_data = self.env['appraisal.criteria.data'].generate_spreadsheet_from_criteria(
            created_criteria,
            self
        )
        
        # Create spreadsheet record
        spreadsheet = self.env['spreadsheet.spreadsheet'].create({
            'name': spreadsheet_name,
            'spreadsheet_binary_data': base64.encodebytes(
                json.dumps(spreadsheet_data).encode('UTF-8')
            ),
            'owner_id': self.env.user.id,
        })
        
        # Link spreadsheet to appraisal
        self.spreadsheet_document_id = spreadsheet.id
        
        # Return action to open spreadsheet directly
        return self.action_view_spreadsheet()
    
    def action_view_criteria(self):
        """Open criteria data for this appraisal"""
        self.ensure_one()
        
        if not self.criteria_loaded:
            raise UserError(_('No criteria loaded yet. Please load criteria first.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Criteria - %s') % self.employee_id.name,
            'res_model': 'appraisal.criteria.data',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('hr_employee_appraisal.view_appraisal_criteria_data_list').id, 'list'),
                (self.env.ref('hr_employee_appraisal.view_appraisal_criteria_data_form').id, 'form'),
            ],
            'domain': [('appraisal_id', '=', self.id)],
            'context': {
                'default_appraisal_id': self.id,
            },
            'target': 'current',
        }
        
    def action_view_spreadsheet(self):
        """Open the linked spreadsheet"""
        self.ensure_one()
        
        if not self.spreadsheet_document_id:
            raise UserError(_('No spreadsheet created yet. Please load criteria first.'))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'action_spreadsheet_oca',
            'params': {
                'spreadsheet_id': self.spreadsheet_document_id.id,
                'model': 'spreadsheet.spreadsheet',
            },
        }
    
    
    def _load_okr_to_spreadsheet(self):
        """Load OKR criteria to spreadsheet format"""
        self.ensure_one()
        
        if not self.okr_template_id or not self.appraisal_team_id:
            return []
        
        template = self.okr_template_id
        team = self.appraisal_team_id
        
        # Get key results based on evaluation type
        if self.evaluation_type == 'department':
            key_results = template.department_key_result_ids.filtered(lambda kr: kr.team_id == team)
            type_prefix = 'okr_dept'
        elif self.evaluation_type == 'role':
            key_results = template.role_key_result_ids.filtered(lambda kr: kr.team_id == team)
            type_prefix = 'okr_role'
        else:  # common
            key_results = template.common_key_result_ids.filtered(lambda kr: kr.team_id == team)
            type_prefix = 'okr_common'
        
        criteria_list = []
        sequence = 1
        
        for kr in key_results:
            criteria_list.append({
                'appraisal_id': self.id,
                'sequence': sequence,
                'objective_breakdown': kr.key_objective_breakdown.objective_item if kr.key_objective_breakdown else '',
                'priority': kr.breakdown_priority or '',
                'metric': kr.metric or '',
                'target_value': kr.target_value,
                'actual_value': kr.actual_value or 0.0,
                # 'achieve': kr.achieve or '',
                'weightage': kr.distributed_weightage,
                'team_name': kr.team_id.name if kr.team_id else '',
                'criteria_type': type_prefix,
            })
            sequence += 1
        
        return criteria_list
    
    def _load_ninebox_to_spreadsheet(self):
        """Load 9-Box criteria to spreadsheet format"""
        self.ensure_one()
        
        if not self.ninebox_template_id or not self.appraisal_team_id:
            return []
        
        template = self.ninebox_template_id
        team = self.appraisal_team_id
        
        criteria_list = []
        sequence = 1
        
        # Get performance lines
        if self.evaluation_type == 'department':
            perf_lines = template.performance_dept_line_ids.filtered(lambda l: l.team_id == team)
            type_prefix = 'ninebox_perf_dept'
        elif self.evaluation_type == 'role':
            perf_lines = template.performance_role_line_ids.filtered(lambda l: l.team_id == team)
            type_prefix = 'ninebox_perf_role'
        else:  # common
            perf_lines = template.performance_common_line_ids.filtered(lambda l: l.team_id == team)
            type_prefix = 'ninebox_perf_common'
        
        for line in perf_lines:
            criteria_list.append({
                'appraisal_id': self.id,
                'sequence': sequence,
                'objective_breakdown': line.objective_breakdown or '',
                'priority': line.priority or '',
                'metric': line.metric or '',
                'target_value': line.target_value,
                'actual_value': line.actual_value or 0.0,
                # 'achieve': line.achieve or '',
                'weightage': line.distributed_weightage,
                'team_name': line.team_id.name if line.team_id else '',
                'criteria_type': type_prefix,
            })
            sequence += 1
        
        # Get potential lines
        if self.evaluation_type == 'department':
            pot_lines = template.potential_dept_line_ids.filtered(lambda l: l.team_id == team)
            pot_type_prefix = 'ninebox_pot_dept'
        elif self.evaluation_type == 'role':
            pot_lines = template.potential_role_line_ids.filtered(lambda l: l.team_id == team)
            pot_type_prefix = 'ninebox_pot_role'
        else:  # common
            pot_lines = template.potential_common_line_ids.filtered(lambda l: l.team_id == team)
            pot_type_prefix = 'ninebox_pot_common'
        
        for line in pot_lines:
            criteria_list.append({
                'appraisal_id': self.id,
                'sequence': sequence,
                'objective_breakdown': line.objective_breakdown or '',
                'priority': line.priority or '',
                'metric': line.metric or '',
                'target_value': line.target_value,
                'actual_value': line.actual_value or 0.0,
                # 'achieve': line.achieve or '',
                'weightage': line.distributed_weightage,
                'team_name': line.team_id.name if line.team_id else '',
                'criteria_type': pot_type_prefix,
            })
            sequence += 1
        
        return criteria_list
    
    # def action_open_spreadsheet(self):
    #     """Open criteria in editable list view - OCA Spreadsheet compatible"""
    #     self.ensure_one()
        
    #     if not self.criteria_loaded:
    #         raise UserError(_('Please load criteria first using "Load to Editable Table" button.'))
        
    #     # Clean context - no group_by, no extra fields
    #     clean_context = {
    #         'default_appraisal_id': self.id,
    #         'create': False,
    #         'delete': False,
    #         # Explicitly disable grouping
    #         'group_by': False,
    #         'group_by_no_leaf': False,
    #         # Help OCA spreadsheet import
    #         'active_model': 'appraisal.criteria.data',
    #     }
        
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': self.spreadsheet_name or _('Appraisal Criteria'),
    #         'res_model': 'appraisal.criteria.data',
    #         'view_mode': 'list,form',
    #         'views': [
    #             (self.env.ref('hr_employee_appraisal.view_appraisal_criteria_data_list').id, 'list'),
    #             (False, 'form')
    #         ],
    #         'domain': [('appraisal_id', '=', self.id)],
    #         'context': clean_context,
    #         'target': 'current',
    #     }


    def _generate_okr_criteria_html(self):
        """Generate HTML table for OKR criteria - ALL COLUMNS"""
        self.ensure_one()
        
        if not self.okr_template_id or not self.appraisal_team_id:
            return '<p class="text-muted">No OKR template or team found.</p>'
        
        template = self.okr_template_id
        team = self.appraisal_team_id
        
        # Get key results based on evaluation type
        if self.evaluation_type == 'department':
            key_results = template.department_key_result_ids.filtered(
                lambda kr: kr.team_id == team
            )
        elif self.evaluation_type == 'role':
            key_results = template.role_key_result_ids.filtered(
                lambda kr: kr.team_id == team
            )
        else:  # common
            key_results = template.common_key_result_ids.filtered(
                lambda kr: kr.team_id == team
            )
        
        if not key_results:
            return f'<p class="text-warning">No {self.evaluation_type} criteria found for team {team.name}.</p>'
        
        # Build HTML table with ALL columns
        html = f'''
        <div class="table-responsive">
            <h4 class="text-primary">
                <i class="fa fa-trophy"></i> 
                {dict(self._fields['evaluation_type'].selection).get(self.evaluation_type)} - OKR Criteria
            </h4>
            <table class="table table-bordered table-striped table-sm">
                <thead class="table-primary">
                    <tr>
                        <th>#</th>
                        <th>Objective Breakdown</th>
                        <th>Priority</th>
                        <th>Metric</th>
                        <th>Target</th>
                        <th>Actual</th>
                        
                        <th class="text-end">Weightage (%)</th>
                        <th>Team</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        sequence = 1
        for kr in key_results:
            # Objective
            objective = kr.key_objective_breakdown.objective_item if kr.key_objective_breakdown else '<span class="text-muted">-</span>'
            
            # Priority
            priority = kr.breakdown_priority if kr.breakdown_priority else '<span class="text-muted">-</span>'
            
            # Metric
            metric = kr.metric if kr.metric else '<span class="text-muted">-</span>'
            
            # Target Display (Operator + Value + Unit + Period)
            target_parts = []
            if kr.target_operator:
                operator_map = {'eq': '=', 'ne': '≠', 'gt': '>', 'lt': '<', 'gte': '≥', 'lte': '≤'}
                target_parts.append(operator_map.get(kr.target_operator, ''))
            target_parts.append(f'{kr.target_value:.2f}')
            if kr.target_unit:
                target_parts.append(kr.target_unit)
            if kr.target_period:
                target_parts.append(f'({kr.target_period})')
            target_display = ' '.join(target_parts) if target_parts else '<span class="text-muted">-</span>'
            
            # Actual Display (Operator + Value + Unit + Period)
            actual_parts = []
            if kr.actual_value:
                if kr.actual_operator:
                    operator_map = {'eq': '=', 'ne': '≠', 'gt': '>', 'lt': '<', 'gte': '≥', 'lte': '≤'}
                    actual_parts.append(operator_map.get(kr.actual_operator, ''))
                actual_parts.append(f'{kr.actual_value:.2f}')
                if kr.actual_unit:
                    actual_parts.append(kr.actual_unit)
                if kr.actual_period:
                    actual_parts.append(f'({kr.actual_period})')
                actual_display = ' '.join(actual_parts)
            else:
                actual_display = '<span class="text-muted">-</span>'
            
            # Achieve
            # achieve = kr.achieve if kr.achieve else '<span class="text-muted">-</span>'
            
            # Weightage
            weightage = f'{kr.distributed_weightage:.2f}' if kr.distributed_weightage else '<span class="text-muted">0.00</span>'
            
            # Team
            team_name = kr.team_id.name if kr.team_id else '<span class="text-muted">-</span>'
            
            html += f'''
                <tr>
                    <td class="text-center">{sequence}</td>
                    <td><strong>{objective}</strong></td>
                    <td>{priority}</td>
                    <td>{metric}</td>
                    <td>{target_display}</td>
                    <td>{actual_display}</td>
                    
                    <td class="text-end"><span class="badge bg-info">{weightage}%</span></td>
                    <td><small>{team_name}</small></td>
                </tr>
            '''
            sequence += 1
        
        # Add totals row
        total_weightage = sum(kr.distributed_weightage for kr in key_results)
        html += f'''
                <tr class="table-info fw-bold">
                    <td colspan="7" class="text-end">TOTAL:</td>
                    <td class="text-end"><span class="badge bg-primary">{total_weightage:.2f}%</span></td>
                    <td></td>
                </tr>
            </tbody>
            </table>
        </div>
        '''
        
        return html
    
    def _generate_ninebox_criteria_html(self):
        """Generate HTML table for 9-Box criteria - ALL COLUMNS"""
        self.ensure_one()
        
        if not self.ninebox_template_id or not self.appraisal_team_id:
            return '<p class="text-muted">No 9-Box template or team found.</p>'
        
        template = self.ninebox_template_id
        team = self.appraisal_team_id
        
        # Get performance criteria
        if self.evaluation_type == 'department':
            perf_lines = template.performance_dept_line_ids.filtered(lambda l: l.team_id == team)
        elif self.evaluation_type == 'role':
            perf_lines = template.performance_role_line_ids.filtered(lambda l: l.team_id == team)
        else:  # common
            perf_lines = template.performance_common_line_ids.filtered(lambda l: l.team_id == team)
        
        # Get potential criteria
        if self.evaluation_type == 'department':
            pot_lines = template.potential_dept_line_ids.filtered(lambda l: l.team_id == team)
        elif self.evaluation_type == 'role':
            pot_lines = template.potential_role_line_ids.filtered(lambda l: l.team_id == team)
        else:  # common
            pot_lines = template.potential_common_line_ids.filtered(lambda l: l.team_id == team)
        
        html = f'''
        <div class="table-responsive">
            <h4 class="text-primary">
                <i class="fa fa-th"></i> 
                {dict(self._fields['evaluation_type'].selection).get(self.evaluation_type)} - 9-Box Grid Criteria
            </h4>
        '''
        
        # Performance Table
        if perf_lines:
            html += '''
            <h5 class="text-success mt-3"><i class="fa fa-line-chart"></i> Performance Criteria</h5>
            <table class="table table-bordered table-striped table-sm">
                <thead class="table-success">
                    <tr>
                        <th>#</th>
                        <th>Objective Breakdown</th>
                        <th>Priority</th>
                        <th>Metric</th>
                        <th class="text-end">Target Value</th>
                        <th class="text-end">Actual Value</th>
                        
                        <th class="text-end">Weightage (%)</th>
                        <th>Team</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            sequence = 1
            for line in perf_lines:
                objective = line.objective_breakdown if line.objective_breakdown else '<span class="text-muted">-</span>'
                priority = line.priority if line.priority else '<span class="text-muted">-</span>'
                metric = line.metric if line.metric else '<span class="text-muted">-</span>'
                target = f'{line.target_value:.2f}' if line.target_value else '<span class="text-muted">0.00</span>'
                actual = f'{line.actual_value:.2f}' if line.actual_value else '<span class="text-muted">-</span>'
                # achieve = line.achieve if line.achieve else '<span class="text-muted">-</span>'
                weightage = f'{line.distributed_weightage:.2f}' if line.distributed_weightage else '<span class="text-muted">0.00</span>'
                team_name = line.team_id.name if line.team_id else '<span class="text-muted">-</span>'
                
                html += f'''
                    <tr>
                        <td class="text-center">{sequence}</td>
                        <td><strong>{objective}</strong></td>
                        <td>{priority}</td>
                        <td>{metric}</td>
                        <td class="text-end">{target}</td>
                        <td class="text-end">{actual}</td>
                        
                        <td class="text-end"><span class="badge bg-success">{weightage}%</span></td>
                        <td><small>{team_name}</small></td>
                    </tr>
                '''
                sequence += 1
            
            # Performance totals
            perf_total = sum(line.distributed_weightage for line in perf_lines)
            html += f'''
                <tr class="table-success fw-bold">
                    <td colspan="7" class="text-end">TOTAL:</td>
                    <td class="text-end"><span class="badge bg-primary">{perf_total:.2f}%</span></td>
                    <td></td>
                </tr>
                </tbody>
            </table>
            '''
        
        # Potential Table
        if pot_lines:
            html += '''
            <h5 class="text-info mt-3"><i class="fa fa-rocket"></i> Potential Criteria</h5>
            <table class="table table-bordered table-striped table-sm">
                <thead class="table-info">
                    <tr>
                        <th>#</th>
                        <th>Objective Breakdown</th>
                        <th>Priority</th>
                        <th>Metric</th>
                        <th class="text-end">Target Value</th>
                        <th class="text-end">Actual Value</th>
                        
                        <th class="text-end">Weightage (%)</th>
                        <th>Team</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            sequence = 1
            for line in pot_lines:
                objective = line.objective_breakdown if line.objective_breakdown else '<span class="text-muted">-</span>'
                priority = line.priority if line.priority else '<span class="text-muted">-</span>'
                metric = line.metric if line.metric else '<span class="text-muted">-</span>'
                target = f'{line.target_value:.2f}' if line.target_value else '<span class="text-muted">0.00</span>'
                actual = f'{line.actual_value:.2f}' if line.actual_value else '<span class="text-muted">-</span>'
                # achieve = line.achieve if line.achieve else '<span class="text-muted">-</span>'
                weightage = f'{line.distributed_weightage:.2f}' if line.distributed_weightage else '<span class="text-muted">0.00</span>'
                team_name = line.team_id.name if line.team_id else '<span class="text-muted">-</span>'
                
                html += f'''
                    <tr>
                        <td class="text-center">{sequence}</td>
                        <td><strong>{objective}</strong></td>
                        <td>{priority}</td>
                        <td>{metric}</td>
                        <td class="text-end">{target}</td>
                        <td class="text-end">{actual}</td>
                        
                        <td class="text-end"><span class="badge bg-info">{weightage}%</span></td>
                        <td><small>{team_name}</small></td>
                    </tr>
                '''
                sequence += 1
            
            # Potential totals
            pot_total = sum(line.distributed_weightage for line in pot_lines)
            html += f'''
                <tr class="table-info fw-bold">
                    <td colspan="7" class="text-end">TOTAL:</td>
                    <td class="text-end"><span class="badge bg-primary">{pot_total:.2f}%</span></td>
                    <td></td>
                </tr>
                </tbody>
            </table>
            '''
        
        if not perf_lines and not pot_lines:
            html += f'<p class="text-warning">No {self.evaluation_type} criteria found for team {team.name}.</p>'
        
        html += '</div>'
        
        return html