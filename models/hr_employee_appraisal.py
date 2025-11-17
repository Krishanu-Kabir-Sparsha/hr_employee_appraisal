# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

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
    
    def _generate_okr_criteria_html(self):
        """Generate HTML table for OKR criteria"""
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
        
        # Build HTML table
        html = f'''
        <div class="table-responsive">
            <h4 class="text-primary">
                <i class="fa fa-trophy"></i> 
                {dict(self._fields['evaluation_type'].selection).get(self.evaluation_type)} - OKR Criteria
            </h4>
            <table class="table table-bordered table-striped">
                <thead class="table-primary">
                    <tr>
                        <th>Objective</th>
                        <th>Metric</th>
                        <th class="text-end">Target Value</th>
                        <th class="text-end">Weightage (%)</th>
                        <th>Priority</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for kr in key_results:
            objective = kr.key_objective_breakdown.objective_item if kr.key_objective_breakdown else 'N/A'
            
            # ✅ FIX: Get metric label - simple approach
            metric_label = kr.metric if kr.metric else 'N/A'
            
            # ✅ FIX: Get priority label - use related field directly
            priority_label = kr.breakdown_priority if kr.breakdown_priority else 'N/A'
            
            html += f'''
                <tr>
                    <td><strong>{objective}</strong></td>
                    <td>{metric_label}</td>
                    <td class="text-end">{kr.target_value:.2f}</td>
                    <td class="text-end"><span class="badge bg-info">{kr.distributed_weightage:.2f}%</span></td>
                    <td>{priority_label}</td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
    
    def _generate_ninebox_criteria_html(self):
        """Generate HTML table for 9-Box criteria"""
        self.ensure_one()
        
        if not self.ninebox_template_id or not self.appraisal_team_id:
            return '<p class="text-muted">No 9-Box template or team found.</p>'
        
        template = self.ninebox_template_id
        team = self.appraisal_team_id
        
        # Get performance criteria
        if self.evaluation_type == 'department':
            perf_lines = template.performance_dept_line_ids.filtered(
                lambda l: l.team_id == team
            )
        elif self.evaluation_type == 'role':
            perf_lines = template.performance_role_line_ids.filtered(
                lambda l: l.team_id == team
            )
        else:  # common
            perf_lines = template.performance_common_line_ids.filtered(
                lambda l: l.team_id == team
            )
        
        # Get potential criteria
        if self.evaluation_type == 'department':
            pot_lines = template.potential_dept_line_ids.filtered(
                lambda l: l.team_id == team
            )
        elif self.evaluation_type == 'role':
            pot_lines = template.potential_role_line_ids.filtered(
                lambda l: l.team_id == team
            )
        else:  # common
            pot_lines = template.potential_common_line_ids.filtered(
                lambda l: l.team_id == team
            )
        
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
            <table class="table table-bordered table-striped">
                <thead class="table-success">
                    <tr>
                        <th>Objective</th>
                        <th>Metric</th>
                        <th class="text-end">Target Value</th>
                        <th class="text-end">Weightage (%)</th>
                        <th>Priority</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            for line in perf_lines:
                # ✅ FIX: Simple direct access
                metric_label = line.metric if line.metric else 'N/A'
                priority_label = line.priority if line.priority else 'N/A'
                
                html += f'''
                    <tr>
                        <td><strong>{line.objective_breakdown or "N/A"}</strong></td>
                        <td>{metric_label}</td>
                        <td class="text-end">{line.target_value:.2f}</td>
                        <td class="text-end"><span class="badge bg-success">{line.distributed_weightage:.2f}%</span></td>
                        <td>{priority_label}</td>
                    </tr>
                '''
            
            html += '''
                </tbody>
            </table>
            '''
        
        # Potential Table
        if pot_lines:
            html += '''
            <h5 class="text-info mt-3"><i class="fa fa-rocket"></i> Potential Criteria</h5>
            <table class="table table-bordered table-striped">
                <thead class="table-info">
                    <tr>
                        <th>Objective</th>
                        <th>Metric</th>
                        <th class="text-end">Target Value</th>
                        <th class="text-end">Weightage (%)</th>
                        <th>Priority</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            for line in pot_lines:
                # ✅ FIX: Simple direct access
                metric_label = line.metric if line.metric else 'N/A'
                priority_label = line.priority if line.priority else 'N/A'
                
                html += f'''
                    <tr>
                        <td><strong>{line.objective_breakdown or "N/A"}</strong></td>
                        <td>{metric_label}</td>
                        <td class="text-end">{line.target_value:.2f}</td>
                        <td class="text-end"><span class="badge bg-info">{line.distributed_weightage:.2f}%</span></td>
                        <td>{priority_label}</td>
                    </tr>
                '''
            
            html += '''
                </tbody>
            </table>
            '''
        
        if not perf_lines and not pot_lines:
            html += f'<p class="text-warning">No {self.evaluation_type} criteria found for team {team.name}.</p>'
        
        html += '</div>'
        
        return html