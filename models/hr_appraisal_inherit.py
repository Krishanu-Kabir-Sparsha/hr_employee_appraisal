# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrAppraisalInherit(models.Model):
    """
    Inherit hr.appraisal from oh_appraisal to add:
    1. Badge ID field for quick employee lookup
    2. OKR/9-Box template selection (filtered by employee's teams)
    3. Internal link buttons to templates
    """
    _inherit = 'hr.appraisal'

    def _auto_init(self):
        """
        Handle column type changes for employee_badge_id
        """
        cr = self.env.cr
        cr.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'hr_appraisal' 
            AND column_name = 'employee_badge_id'
        """)
        result = cr.fetchone()
        # If column exists and is NOT integer (Many2one), drop it
        if result and result[0] != 'integer':
            cr.execute("""
                ALTER TABLE hr_appraisal 
                DROP COLUMN IF EXISTS employee_badge_id
            """)
            _logger.info("Dropped old employee_badge_id column for Many2one field")
        
        return super()._auto_init()

    # ============ BADGE ID SELECTION ============
    employee_badge_id = fields.Many2one(
        'employee.badge',
        string='Employee Badge ID',
        help="Select employee by Badge ID - supports Search More and type to filter"
    )
    
    # ============ EMPLOYEE'S TEAMS (for domain filtering) ============
    employee_team_ids = fields.Many2many(
        'oh.appraisal.team',
        string='Employee Teams',
        compute='_compute_employee_teams',
        store=False,
        help="Teams the selected employee belongs to"
    )
    
    # ============ AVAILABLE TEMPLATES (computed based on employee's teams) ============
    available_okr_template_ids = fields.Many2many(
        'oh.appraisal.okr.template',
        string='Available OKR Templates',
        compute='_compute_available_templates',
        store=False
    )
    
    available_ninebox_template_ids = fields.Many2many(
        'oh.appraisal.ninebox.template',
        string='Available 9-Box Templates',
        compute='_compute_available_templates',
        store=False
    )
    
    # ============ TEMPLATE SELECTION ============
    appraisal_template_type = fields.Selection([
        ('survey', 'Survey Form'),
        ('okr', 'OKR Template'),
        ('ninebox', '9-Box Grid Template')
    ], string='Appraisal Type', default='survey',
       help="Select the type of appraisal template to use")
    
    # Survey selection (from survey module)
    survey_id = fields.Many2one(
        'survey.survey',
        string='Select Appraisal Form',
        domain="[('active', '=', True)]",
        help="Select a survey form for this appraisal"
    )
    
    evaluation_type_ids = fields.Many2many(
        'appraisal.evaluation.type',
        string='Evaluation Types',
        help="Select one or more evaluation types to load criteria"
    )
    
    # Add computed display field
    evaluation_types_display = fields.Char(
        compute='_compute_evaluation_display',
        string='Selected Evaluations'
    )
    
    @api.depends('evaluation_type_ids')
    def _compute_evaluation_display(self):
        for record in self:
            if record.evaluation_type_ids:
                types = record.evaluation_type_ids.mapped('name')
                record.evaluation_types_display = ', '.join(types)
            else:
                record.evaluation_types_display = False
    
    okr_template_id = fields.Many2one(
        'oh.appraisal.okr.template',
        string='OKR Template',
        domain="[('id', 'in', available_okr_template_ids)]",
        help="Select an OKR template for this appraisal"
    )
    
    ninebox_template_id = fields.Many2one(
        'oh.appraisal.ninebox.template',
        string='9-Box Template',
        domain="[('id', 'in', available_ninebox_template_ids)]",
        help="Select a 9-Box Grid template for this appraisal"
    )
    
    # Display field for selected template name
    selected_template_display = fields.Char(
        string='Selected Template',
        compute='_compute_selected_template_display',
        store=True
    )
    
    # Helper field to show if templates are available
    has_okr_templates = fields.Boolean(
        compute='_compute_available_templates',
        store=False
    )
    has_ninebox_templates = fields.Boolean(
        compute='_compute_available_templates',
        store=False
    )
    no_templates_message = fields.Char(
        compute='_compute_available_templates',
        store=False
    )
    
    # ============ COMPUTE METHODS ============
    @api.depends('employee_id')
    def _compute_employee_teams(self):
        """Get all teams the employee belongs to"""
        for record in self:
            if record.employee_id:
                # Search for teams where this employee is a member
                teams = self.env['oh.appraisal.team'].search([
                    ('member_ids', 'in', record.employee_id.id)
                ])
                record.employee_team_ids = teams
            else:
                record.employee_team_ids = False
    
    @api.depends('employee_id', 'employee_team_ids')
    def _compute_available_templates(self):
        """Compute available OKR and 9-Box templates based on employee's teams"""
        for record in self:
            okr_templates = self.env['oh.appraisal.okr.template']
            ninebox_templates = self.env['oh.appraisal.ninebox.template']
            
            if record.employee_id:
                # Get employee's teams
                employee_team_ids = record.employee_team_ids.ids
                
                if employee_team_ids:
                    # Find OKR templates that have weightages for employee's teams
                    okr_weightages = self.env['oh.appraisal.okr.weightage'].search([
                        ('team_id', 'in', employee_team_ids)
                    ])
                    okr_template_ids = okr_weightages.mapped('okr_template_id').filtered(
                        lambda t: t.active
                    )
                    okr_templates = okr_template_ids
                    
                    # Find 9-Box templates that have weightages for employee's teams
                    # Check both performance and potential weightages
                    ninebox_perf_weightages = self.env['oh.appraisal.ninebox.weightage'].search([
                        ('team_id', 'in', employee_team_ids),
                        ('type', '=', 'performance')
                    ])
                    ninebox_pot_weightages = self.env['oh.appraisal.ninebox.weightage'].search([
                        ('team_id', 'in', employee_team_ids),
                        ('type', '=', 'potential')
                    ])
                    
                    ninebox_template_ids = (
                        ninebox_perf_weightages.mapped('template_id') | 
                        ninebox_pot_weightages.mapped('template_id')
                    ).filtered(lambda t: t.active)
                    ninebox_templates = ninebox_template_ids
            
            record.available_okr_template_ids = okr_templates
            record.available_ninebox_template_ids = ninebox_templates
            record.has_okr_templates = bool(okr_templates)
            record.has_ninebox_templates = bool(ninebox_templates)
            
            # Generate message if no templates available
            if record.employee_id and not okr_templates and not ninebox_templates:
                if not record.employee_team_ids:
                    record.no_templates_message = _("Employee is not assigned to any team. Please assign the employee to a team first.")
                else:
                    team_names = ', '.join(record.employee_team_ids.mapped('name'))
                    record.no_templates_message = _("No OKR or 9-Box templates found for teams: %s") % team_names
            else:
                record.no_templates_message = False
    
    @api.depends('okr_template_id', 'ninebox_template_id', 'appraisal_template_type')
    def _compute_selected_template_display(self):
        """Compute display name for selected template"""
        for record in self:
            if record.appraisal_template_type == 'okr' and record.okr_template_id:
                record.selected_template_display = f"[OKR] {record.okr_template_id.name}"
            elif record.appraisal_template_type == 'ninebox' and record.ninebox_template_id:
                record.selected_template_display = f"[9-Box] {record.ninebox_template_id.name}"
            elif record.appraisal_template_type == 'survey':
                record.selected_template_display = "Survey Form"
            else:
                record.selected_template_display = False
    
    # ============ ONCHANGE METHODS ============
    @api.onchange('employee_badge_id')
    def _onchange_employee_badge_id(self):
        """Auto-select employee when Badge ID is selected from dropdown"""
        if self.employee_badge_id and self.employee_badge_id.employee_id:
            self.employee_id = self.employee_badge_id.employee_id.id
            # Clear previous template selections as they may not be valid for new employee
            self.with_context(clear_all_templates=True)._clear_template_selections()
            # Auto-detect templates
            self._auto_detect_templates()
        elif not self.employee_badge_id:
            if not self.employee_id:
                self.employee_id = False
                self.with_context(clear_all_templates=True)._clear_template_selections()
    
    @api.onchange('employee_id')
    def _onchange_employee_id_badge(self):
        """Sync Badge ID dropdown when employee is selected"""
        if self.employee_id and self.employee_id.barcode:
            # Find the badge record for this employee
            badge = self.env['employee.badge'].search([
                ('employee_id', '=', self.employee_id.id)
            ], limit=1)
            if badge:
                self.employee_badge_id = badge.id
            else:
                self.employee_badge_id = False
        elif not self.employee_id:
            self.employee_badge_id = False
        
        # Clear previous template selections when employee changes
        self.with_context(clear_all_templates=True)._clear_template_selections()
        # Auto-detect available templates for this employee
        self._auto_detect_templates()
    
    @api.onchange('appraisal_template_type')
    def _onchange_appraisal_template_type(self):
        """Don't clear selections - just let invisible attributes handle visibility"""
        # Do nothing - preserve all template selections
        # The view's invisible attributes will handle showing/hiding the right fields
        pass
    
    # @api.onchange('okr_template_id')
    # def _onchange_okr_template(self):
    #     """Update template type when OKR template selected"""
    #     if self.okr_template_id:
    #         self.appraisal_template_type = 'okr'
    #         self.ninebox_template_id = False
    
    # @api.onchange('ninebox_template_id')
    # def _onchange_ninebox_template(self):
    #     """Update template type when 9-Box template selected"""
    #     if self.ninebox_template_id:
    #         self.appraisal_template_type = 'ninebox'
    #         self.okr_template_id = False
    
    @api.onchange('okr_template_id')
    def _onchange_okr_template(self):
        """Auto-set template type when OKR template is selected"""
        if self.okr_template_id:
            self.appraisal_template_type = 'okr'
            # Don't clear ninebox_template_id - preserve it
    
    @api.onchange('ninebox_template_id')
    def _onchange_ninebox_template(self):
        """Auto-set template type when 9-Box template is selected"""
        if self.ninebox_template_id:
            self.appraisal_template_type = 'ninebox'
            # Don't clear okr_template_id - preserve it
    
    @api.onchange('survey_id')
    def _onchange_survey_id(self):
        """Auto-set template type when Survey is selected"""
        if self.survey_id:
            self.appraisal_template_type = 'survey'
            # Don't clear okr/ninebox templates - preserve them

    # ============ HELPER METHODS ============
    def _clear_template_selections(self):
        """Clear template selections when employee changes"""
        # Only clear if explicitly needed (e.g., employee change)
        # Don't clear when just switching appraisal types
        if self._context.get('clear_all_templates'):
            self.okr_template_id = False
            self.ninebox_template_id = False
            self.survey_id = False
            # Also clear criteria lines
            self.okr_line_ids.unlink()
            self.ninebox_performance_line_ids.unlink()
            self.ninebox_potential_line_ids.unlink()
            self.criteria_loaded = False
            if self.appraisal_template_type in ('okr', 'ninebox'):
                self.appraisal_template_type = 'survey'
    
    def _auto_detect_templates(self):
        """Auto-detect and suggest templates based on employee's teams"""
        if not self.employee_id:
            return
        
        # Trigger recomputation of available templates
        self._compute_employee_teams()
        self._compute_available_templates()
        
        # Auto-select if only one template type is available
        if self.has_okr_templates and not self.has_ninebox_templates:
            if len(self.available_okr_template_ids) == 1:
                self.okr_template_id = self.available_okr_template_ids[0].id
                self.appraisal_template_type = 'okr'
        elif self.has_ninebox_templates and not self.has_okr_templates:
            if len(self.available_ninebox_template_ids) == 1:
                self.ninebox_template_id = self.available_ninebox_template_ids[0].id
                self.appraisal_template_type = 'ninebox'

    # Helper fields to check if line types exist
    has_dept_okr = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_role_okr = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_common_okr = fields.Boolean(compute='_compute_line_type_existence', store=False)
    
    has_dept_performance = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_role_performance = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_common_performance = fields.Boolean(compute='_compute_line_type_existence', store=False)
    
    has_dept_potential = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_role_potential = fields.Boolean(compute='_compute_line_type_existence', store=False)
    has_common_potential = fields.Boolean(compute='_compute_line_type_existence', store=False)
    
    @api.depends('okr_dept_line_ids', 'okr_role_line_ids', 'okr_common_line_ids',
                 'ninebox_perf_dept_line_ids', 'ninebox_perf_role_line_ids', 'ninebox_perf_common_line_ids',
                 'ninebox_pot_dept_line_ids', 'ninebox_pot_role_line_ids', 'ninebox_pot_common_line_ids')
    def _compute_line_type_existence(self):
        """Check which line types exist for conditional display"""
        for record in self:
            # OKR line types
            record.has_dept_okr = bool(record.okr_dept_line_ids)
            record.has_role_okr = bool(record.okr_role_line_ids)
            record.has_common_okr = bool(record.okr_common_line_ids)
            
            # 9-Box Performance line types
            record.has_dept_performance = bool(record.ninebox_perf_dept_line_ids)
            record.has_role_performance = bool(record.ninebox_perf_role_line_ids)
            record.has_common_performance = bool(record.ninebox_perf_common_line_ids)
            
            # 9-Box Potential line types
            record.has_dept_potential = bool(record.ninebox_pot_dept_line_ids)
            record.has_role_potential = bool(record.ninebox_pot_role_line_ids)
            record.has_common_potential = bool(record.ninebox_pot_common_line_ids)
    
    # ============ ACTION BUTTONS ============
    def action_open_okr_template(self):
        """Open the selected OKR template in a new window"""
        self.ensure_one()
        if not self.okr_template_id:
            raise UserError(_('No OKR template selected.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('OKR Template'),
            'res_model': 'oh.appraisal.okr.template',
            'res_id': self.okr_template_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_open_ninebox_template(self):
        """Open the selected 9-Box template in a new window"""
        self.ensure_one()
        if not self.ninebox_template_id:
            raise UserError(_('No 9-Box template selected.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('9-Box Template'),
            'res_model': 'oh.appraisal.ninebox.template',
            'res_id': self.ninebox_template_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_open_selected_template(self):
        """Open the currently selected template (OKR or 9-Box)"""
        self.ensure_one()
        if self.appraisal_template_type == 'okr' and self.okr_template_id:
            return self.action_open_okr_template()
        elif self.appraisal_template_type == 'ninebox' and self.ninebox_template_id:
            return self.action_open_ninebox_template()
        else:
            raise UserError(_('No template selected to open.'))
    
    # ============ OVERRIDE CREATE/WRITE ============
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle badge ID lookup"""
        for vals in vals_list:
            if vals.get('employee_badge_id') and not vals.get('employee_id'):
                badge = self.env['employee.badge'].browse(vals['employee_badge_id'])
                if badge and badge.employee_id:
                    vals['employee_id'] = badge.employee_id.id
        return super().create(vals_list)
    
    def write(self, vals):
        """Override write to handle badge ID sync"""
        if vals.get('employee_badge_id') and 'employee_id' not in vals:
            badge = self.env['employee.badge'].browse(vals['employee_badge_id'])
            if badge and badge.employee_id:
                vals['employee_id'] = badge.employee_id.id
        return super().write(vals)
    
    # ============ CRITERIA LINES ============
    okr_line_ids = fields.One2many(
        'hr.appraisal.okr.line',
        'appraisal_id',
        string='OKR Criteria Lines'
    )
    
    # Filtered OKR lines by type
    okr_dept_line_ids = fields.One2many(
        'hr.appraisal.okr.line',
        'appraisal_id',
        string='Department OKR Lines',
        domain=[('line_type', '=', 'department')]
    )
    
    okr_role_line_ids = fields.One2many(
        'hr.appraisal.okr.line',
        'appraisal_id',
        string='Role OKR Lines',
        domain=[('line_type', '=', 'role')]
    )
    
    okr_common_line_ids = fields.One2many(
        'hr.appraisal.okr.line',
        'appraisal_id',
        string='Common OKR Lines',
        domain=[('line_type', '=', 'common')]
    )
    
    ninebox_performance_line_ids = fields.One2many(
        'hr.appraisal.ninebox.performance.line',
        'appraisal_id',
        string='9-Box Performance Lines'
    )
    
    # Filtered Performance lines by type
    ninebox_perf_dept_line_ids = fields.One2many(
        'hr.appraisal.ninebox.performance.line',
        'appraisal_id',
        string='Department Performance Lines',
        domain=[('line_type', '=', 'department')]
    )
    
    ninebox_perf_role_line_ids = fields.One2many(
        'hr.appraisal.ninebox.performance.line',
        'appraisal_id',
        string='Role Performance Lines',
        domain=[('line_type', '=', 'role')]
    )
    
    ninebox_perf_common_line_ids = fields.One2many(
        'hr.appraisal.ninebox.performance.line',
        'appraisal_id',
        string='Common Performance Lines',
        domain=[('line_type', '=', 'common')]
    )
    
    ninebox_potential_line_ids = fields.One2many(
        'hr.appraisal.ninebox.potential.line',
        'appraisal_id',
        string='9-Box Potential Lines'
    )
    
    # Filtered Potential lines by type
    ninebox_pot_dept_line_ids = fields.One2many(
        'hr.appraisal.ninebox.potential.line',
        'appraisal_id',
        string='Department Potential Lines',
        domain=[('line_type', '=', 'department')]
    )
    
    ninebox_pot_role_line_ids = fields.One2many(
        'hr.appraisal.ninebox.potential.line',
        'appraisal_id',
        string='Role Potential Lines',
        domain=[('line_type', '=', 'role')]
    )
    
    ninebox_pot_common_line_ids = fields.One2many(
        'hr.appraisal.ninebox.potential.line',
        'appraisal_id',
        string='Common Potential Lines',
        domain=[('line_type', '=', 'common')]
    )
    
    # ============ SCORES & CALCULATIONS ============
    criteria_loaded = fields.Boolean('Criteria Loaded', default=False)
    
    total_okr_score = fields.Float(
        'Total OKR Score',
        compute='_compute_total_scores',
        store=True,
        digits=(5, 2)
    )
    
    total_performance_score = fields.Float(
        'Total Performance Score',
        compute='_compute_total_scores',
        store=True,
        digits=(5, 2)
    )
    
    total_potential_score = fields.Float(
        'Total Potential Score',
        compute='_compute_total_scores',
        store=True,
        digits=(5, 2)
    )
    
    final_score = fields.Float(
        'Final Score',
        compute='_compute_final_score',
        store=True,
        digits=(5, 2)
    )
    
    performance_rating = fields.Selection([
        ('outstanding', 'Outstanding'),
        ('exceeds', 'Exceeds Expectations'),
        ('meets', 'Meets Expectations'),
        ('needs_improvement', 'Needs Improvement'),
        ('unsatisfactory', 'Unsatisfactory')
    ], string='Performance Rating', compute='_compute_performance_rating', store=True)
    
    # ============ SPREADSHEET ============
    spreadsheet_id = fields.Many2one(
        'spreadsheet.spreadsheet',
        string='Appraisal Spreadsheet',
        help="Auto-generated spreadsheet for this appraisal"
    )
    
    # Add these compute methods
    
    @api.depends('okr_line_ids.weighted_score', 
                 'ninebox_performance_line_ids.weighted_score',
                 'ninebox_potential_line_ids.weighted_score')
    def _compute_total_scores(self):
        """Calculate total scores for each section"""
        for record in self:
            record.total_okr_score = sum(record.okr_line_ids.mapped('weighted_score'))
            record.total_performance_score = sum(record.ninebox_performance_line_ids.mapped('weighted_score'))
            record.total_potential_score = sum(record.ninebox_potential_line_ids.mapped('weighted_score'))
    
    @api.depends('total_okr_score', 'total_performance_score', 'total_potential_score', 'appraisal_template_type')
    def _compute_final_score(self):
        """Calculate final score based on template type"""
        for record in self:
            if record.appraisal_template_type == 'okr':
                record.final_score = record.total_okr_score
            elif record.appraisal_template_type == 'ninebox':
                # Average of performance and potential
                if record.total_performance_score or record.total_potential_score:
                    record.final_score = (record.total_performance_score + record.total_potential_score) / 2
                else:
                    record.final_score = 0.0
            else:
                record.final_score = 0.0
    
    @api.depends('final_score')
    def _compute_performance_rating(self):
        """Calculate performance rating based on final score"""
        for record in self:
            if record.final_score >= 90:
                record.performance_rating = 'outstanding'
            elif record.final_score >= 75:
                record.performance_rating = 'exceeds'
            elif record.final_score >= 60:
                record.performance_rating = 'meets'
            elif record.final_score >= 40:
                record.performance_rating = 'needs_improvement'
            else:
                record.performance_rating = 'unsatisfactory'
    
    # Add these action methods
    
    def action_load_criteria(self):
        """Load criteria from selected template"""
        self.ensure_one()
        
        if not self.employee_id:
            raise UserError(_('Please select an employee first.'))
        
        if not self.evaluation_type_ids:
            raise UserError(_('Please select at least one Evaluation Type.'))
        
        if self.appraisal_template_type == 'okr' and self.okr_template_id:
            self._load_okr_criteria()
        elif self.appraisal_template_type == 'ninebox' and self.ninebox_template_id:
            self._load_ninebox_criteria()
        else:
            raise UserError(_('Please select a template first.'))
        
        self.criteria_loaded = True
        
        # Auto-refresh the view
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def _load_okr_criteria(self):
        """Load OKR key results from template based on selected evaluation types"""
        self.ensure_one()
        
        if not self.evaluation_type_ids:
            raise UserError(_('Please select at least one Evaluation Type first.'))
        
        # Clear existing lines
        self.okr_line_ids.unlink()
        
        template = self.okr_template_id
        employee_teams = self.employee_team_ids
        
        criteria_vals = []
        sequence = 1
        
        # Load for each selected evaluation type
        for eval_type in self.evaluation_type_ids:
            if eval_type.code == 'department':
                key_results = template.department_key_result_ids.filtered(
                    lambda kr: kr.team_id in employee_teams
                )
            elif eval_type.code == 'role':
                key_results = template.role_key_result_ids.filtered(
                    lambda kr: kr.team_id in employee_teams
                )
            else:  # common
                key_results = template.common_key_result_ids.filtered(
                    lambda kr: kr.team_id in employee_teams
                )
            
            for kr in key_results:
                criteria_vals.append({
                    'appraisal_id': self.id,
                    'sequence': sequence,
                    'line_type': eval_type.code,
                    'objective_breakdown': kr.key_objective_breakdown.objective_item if kr.key_objective_breakdown else '',
                    'priority': kr.breakdown_priority,
                    'metric': kr.metric,
                    'target_value': kr.target_value,
                    'target_unit': kr.target_unit,
                    'actual_value': kr.actual_value or 0.0,
                    'actual_unit': kr.actual_unit,
                    'weightage': kr.distributed_weightage,
                    'team_id': kr.team_id.id,
                })
                sequence += 1
        
        if criteria_vals:
            self.env['hr.appraisal.okr.line'].create(criteria_vals)
    
    def _load_ninebox_criteria(self):
        """Load 9-Box performance and potential criteria from template based on selected evaluation types"""
        self.ensure_one()
        
        if not self.evaluation_type_ids:
            raise UserError(_('Please select at least one Evaluation Type first.'))
        
        # Clear existing lines
        self.ninebox_performance_line_ids.unlink()
        self.ninebox_potential_line_ids.unlink()
        
        template = self.ninebox_template_id
        employee_teams = self.employee_team_ids
        
        # Load for each selected evaluation type
        for eval_type in self.evaluation_type_ids:
            # Load Performance Lines
            perf_vals = []
            sequence = 1
            
            if eval_type.code == 'department':
                perf_lines = template.performance_dept_line_ids.filtered(lambda l: l.team_id in employee_teams)
            elif eval_type.code == 'role':
                perf_lines = template.performance_role_line_ids.filtered(lambda l: l.team_id in employee_teams)
            else:  # common
                perf_lines = template.performance_common_line_ids.filtered(lambda l: l.team_id in employee_teams)
            
            for line in perf_lines:
                perf_vals.append({
                    'appraisal_id': self.id,
                    'sequence': sequence,
                    'line_type': eval_type.code,
                    'objective_breakdown': line.objective_breakdown,
                    'priority': line.priority,
                    'metric': line.metric,
                    'target_value': line.target_value,
                    'actual_value': line.actual_value or 0.0,
                    'weightage': line.distributed_weightage,
                    'team_id': line.team_id.id,
                })
                sequence += 1
            
            if perf_vals:
                self.env['hr.appraisal.ninebox.performance.line'].create(perf_vals)
            
            # Load Potential Lines
            pot_vals = []
            sequence = 1
            
            if eval_type.code == 'department':
                pot_lines = template.potential_dept_line_ids.filtered(lambda l: l.team_id in employee_teams)
            elif eval_type.code == 'role':
                pot_lines = template.potential_role_line_ids.filtered(lambda l: l.team_id in employee_teams)
            else:  # common
                pot_lines = template.potential_common_line_ids.filtered(lambda l: l.team_id in employee_teams)
            
            for line in pot_lines:
                pot_vals.append({
                    'appraisal_id': self.id,
                    'sequence': sequence,
                    'line_type': eval_type.code,
                    'objective_breakdown': line.objective_breakdown,
                    'priority': line.priority,
                    'metric': line.metric,
                    'target_value': line.target_value,
                    'actual_value': line.actual_value or 0.0,
                    'weightage': line.distributed_weightage,
                    'team_id': line.team_id.id,
                })
                sequence += 1
            
            if pot_vals:
                self.env['hr.appraisal.ninebox.potential.line'].create(pot_vals)

    @api.onchange('evaluation_type_ids')
    def _onchange_evaluation_type_ids(self):
        """Clear criteria when evaluation types change"""
        if self.criteria_loaded:
            self.okr_line_ids.unlink()
            self.ninebox_performance_line_ids.unlink()
            self.ninebox_potential_line_ids.unlink()
            self.criteria_loaded = False
    
    def action_generate_spreadsheet(self):
        """Generate OCA Spreadsheet from loaded criteria"""
        self.ensure_one()
        
        if not self.criteria_loaded:
            raise UserError(_('Please load criteria first before generating spreadsheet.'))
        
        import json
        import base64
        
        # Get locale
        lang = self.env['res.lang']._lang_get(self.env.user.lang)
        locale = lang._odoo_lang_to_spreadsheet_locale()
        
        # Generate spreadsheet data based on template type
        if self.appraisal_template_type == 'okr':
            spreadsheet_data = self._generate_okr_spreadsheet(locale)
        elif self.appraisal_template_type == 'ninebox':
            spreadsheet_data = self._generate_ninebox_spreadsheet(locale)
        else:
            raise UserError(_('Invalid template type for spreadsheet generation.'))
        
        # Create spreadsheet name
        employee_name = self.employee_id.name
        template_type = dict(self._fields['appraisal_template_type'].selection).get(
            self.appraisal_template_type, 'Appraisal'
        )
        timestamp = fields.Datetime.now().strftime('%Y-%m-%d %H:%M')
        spreadsheet_name = f"{employee_name} - {template_type} Appraisal ({timestamp})"
        
        # Create or update spreadsheet
        if self.spreadsheet_id:
            self.spreadsheet_id.write({
                'name': spreadsheet_name,
                'spreadsheet_binary_data': base64.encodebytes(
                    json.dumps(spreadsheet_data).encode('UTF-8')
                ),
            })
        else:
            spreadsheet = self.env['spreadsheet.spreadsheet'].create({
                'name': spreadsheet_name,
                'spreadsheet_binary_data': base64.encodebytes(
                    json.dumps(spreadsheet_data).encode('UTF-8')
                ),
                'owner_id': self.env.user.id,
            })
            self.spreadsheet_id = spreadsheet.id
        
        return self.action_open_spreadsheet()
    
    def _generate_okr_spreadsheet(self, locale):
        """Generate spreadsheet for OKR criteria"""
        cells = {}
        headers = ['Seq', 'Type', 'Objective', 'Priority', 'Metric', 'Target', 'Actual', 'Achievement %', 'Weightage %', 'Weighted Score', 'Team']
        
        # Header row
        for col_idx, header in enumerate(headers):
            col_letter = self._number_to_column(col_idx)
            cells[f'{col_letter}1'] = {
                'content': header,
                'style': 1
            }
        
        # Data rows
        for row_idx, line in enumerate(self.okr_line_ids.sorted('sequence'), start=2):
            data = [
                line.sequence,
                dict(line._fields['line_type'].selection).get(line.line_type),
                line.objective_breakdown,
                dict(line._fields['priority'].selection).get(line.priority) if line.priority else '',
                dict(line._fields['metric'].selection).get(line.metric) if line.metric else '',
                line.target_value,
                line.actual_value,
                line.achievement_percentage,
                line.weightage,
                line.weighted_score,
                line.team_id.name if line.team_id else '',
            ]
            
            for col_idx, value in enumerate(data):
                col_letter = self._number_to_column(col_idx)
                cell_ref = f'{col_letter}{row_idx}'
                
                if isinstance(value, float):
                    cells[cell_ref] = {'content': str(round(value, 2)), 'format': 1}
                else:
                    cells[cell_ref] = {'content': str(value) if value else ''}
        
        # Totals row
        total_row = len(self.okr_line_ids) + 2
        cells[f'A{total_row}'] = {'content': 'TOTALS:', 'style': 2}
        cells[f'I{total_row}'] = {
            'content': str(round(sum(self.okr_line_ids.mapped('weightage')), 2)),
            'style': 2
        }
        cells[f'J{total_row}'] = {
            'content': str(round(self.total_okr_score, 2)),
            'style': 2
        }
        
        return {
            'version': 16,
            'sheets': [{
                'id': 'okr_sheet',
                'name': 'OKR Criteria',
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
    
    def _generate_ninebox_spreadsheet(self, locale):
        """Generate spreadsheet for 9-Box criteria with separate sheets"""
        sheets = []
        headers = ['Seq', 'Type', 'Objective', 'Priority', 'Metric', 'Target', 'Actual', 'Achievement %', 'Weightage %', 'Weighted Score', 'Team']
        
        # Performance Sheet
        if self.ninebox_performance_line_ids:
            perf_cells = {}
            
            # Header
            for col_idx, header in enumerate(headers):
                col_letter = self._number_to_column(col_idx)
                perf_cells[f'{col_letter}1'] = {'content': header, 'style': 3}
            
            # Data
            for row_idx, line in enumerate(self.ninebox_performance_line_ids.sorted('sequence'), start=2):
                data = [
                    line.sequence,
                    dict(line._fields['line_type'].selection).get(line.line_type),
                    line.objective_breakdown,
                    dict(line._fields['priority'].selection).get(line.priority) if line.priority else '',
                    dict(line._fields['metric'].selection).get(line.metric) if line.metric else '',
                    line.target_value,
                    line.actual_value,
                    line.achievement_percentage,
                    line.weightage,
                    line.weighted_score,
                    line.team_id.name if line.team_id else '',
                ]
                
                for col_idx, value in enumerate(data):
                    col_letter = self._number_to_column(col_idx)
                    if isinstance(value, float):
                        perf_cells[f'{col_letter}{row_idx}'] = {'content': str(round(value, 2)), 'format': 1}
                    else:
                        perf_cells[f'{col_letter}{row_idx}'] = {'content': str(value) if value else ''}
            
            # Totals
            perf_total_row = len(self.ninebox_performance_line_ids) + 2
            perf_cells[f'A{perf_total_row}'] = {'content': 'TOTALS:', 'style': 4}
            perf_cells[f'I{perf_total_row}'] = {
                'content': str(round(sum(self.ninebox_performance_line_ids.mapped('weightage')), 2)),
                'style': 4
            }
            perf_cells[f'J{perf_total_row}'] = {
                'content': str(round(self.total_performance_score, 2)),
                'style': 4
            }
            
            sheets.append({
                'id': 'performance_sheet',
                'name': 'Performance',
                'colNumber': len(headers),
                'rowNumber': perf_total_row,
                'cells': perf_cells,
                'merges': [],
            })
        
        # Potential Sheet
        if self.ninebox_potential_line_ids:
            pot_cells = {}
            
            # Header
            for col_idx, header in enumerate(headers):
                col_letter = self._number_to_column(col_idx)
                pot_cells[f'{col_letter}1'] = {'content': header, 'style': 5}
            
            # Data
            for row_idx, line in enumerate(self.ninebox_potential_line_ids.sorted('sequence'), start=2):
                data = [
                    line.sequence,
                    dict(line._fields['line_type'].selection).get(line.line_type),
                    line.objective_breakdown,
                    dict(line._fields['priority'].selection).get(line.priority) if line.priority else '',
                    dict(line._fields['metric'].selection).get(line.metric) if line.metric else '',
                    line.target_value,
                    line.actual_value,
                    line.achievement_percentage,
                    line.weightage,
                    line.weighted_score,
                    line.team_id.name if line.team_id else '',
                ]
                
                for col_idx, value in enumerate(data):
                    col_letter = self._number_to_column(col_idx)
                    if isinstance(value, float):
                        pot_cells[f'{col_letter}{row_idx}'] = {'content': str(round(value, 2)), 'format': 1}
                    else:
                        pot_cells[f'{col_letter}{row_idx}'] = {'content': str(value) if value else ''}
            
            # Totals
            pot_total_row = len(self.ninebox_potential_line_ids) + 2
            pot_cells[f'A{pot_total_row}'] = {'content': 'TOTALS:', 'style': 6}
            pot_cells[f'I{pot_total_row}'] = {
                'content': str(round(sum(self.ninebox_potential_line_ids.mapped('weightage')), 2)),
                'style': 6
            }
            pot_cells[f'J{pot_total_row}'] = {
                'content': str(round(self.total_potential_score, 2)),
                'style': 6
            }
            
            sheets.append({
                'id': 'potential_sheet',
                'name': 'Potential',
                'colNumber': len(headers),
                'rowNumber': pot_total_row,
                'cells': pot_cells,
                'merges': [],
            })
        
        return {
            'version': 16,
            'sheets': sheets,
            'styles': {
                '1': {'bold': True, 'fillColor': '#4A90E2', 'textColor': '#FFFFFF'},
                '2': {'bold': True, 'fillColor': '#E8F5E9'},
                '3': {'bold': True, 'fillColor': '#4CAF50', 'textColor': '#FFFFFF'},
                '4': {'bold': True, 'fillColor': '#C8E6C9'},
                '5': {'bold': True, 'fillColor': '#2196F3', 'textColor': '#FFFFFF'},
                '6': {'bold': True, 'fillColor': '#BBDEFB'},
            },
            'formats': {'1': '#,##0.00'},
            'borders': {},
            'settings': {'locale': locale},
            'revisionId': 'START_REVISION',
        }
    
    def _number_to_column(self, n):
        """Convert number to Excel column letter"""
        result = ""
        while n >= 0:
            result = chr(65 + (n % 26)) + result
            n = n // 26 - 1
        return result
    
    def action_open_spreadsheet(self):
        """Open the generated spreadsheet"""
        self.ensure_one()
        
        if not self.spreadsheet_id:
            raise UserError(_('No spreadsheet has been generated yet.'))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'action_spreadsheet_oca',
            'params': {
                'spreadsheet_id': self.spreadsheet_id.id,
                'model': 'spreadsheet.spreadsheet',
            },
        }
    
    def action_print_appraisal_report(self):
        """Print appraisal report PDF"""
        self.ensure_one()
        return self.env.ref('hr_employee_appraisal.action_report_appraisal').report_action(self)