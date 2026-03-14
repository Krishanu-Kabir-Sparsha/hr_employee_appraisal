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
        Handle column type changes for employee_badge_id.
        Also fix any existing records with NULL stage_id.
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
        
        res = super()._auto_init()
        
        # Fix existing records with NULL stage_id
        cr.execute("""
            UPDATE hr_appraisal
            SET stage_id = (
                SELECT id FROM hr_appraisal_stages
                ORDER BY sequence ASC LIMIT 1
            )
            WHERE stage_id IS NULL
            AND EXISTS (SELECT 1 FROM hr_appraisal_stages)
        """)
        if cr.rowcount:
            _logger.info("Fixed %d appraisal records with missing stage_id", cr.rowcount)
        
        return res

    # ============ BADGE ID SELECTION ============
    employee_badge_id = fields.Many2one(
        'employee.badge',
        string='Employee Badge ID',
        help="Select employee by Badge ID - supports Search More and type to filter"
    )
    
    # ============ EMPLOYEE INFO (auto-populated from employee) ============
    employee_department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )

    employee_job_id = fields.Many2one(
        'hr.job',
        string='Designation / Position',
        related='employee_id.job_id',
        store=True,
        readonly=True,
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
    
    # Link related appraisals
    appraisal_group_id = fields.Char(
        'Appraisal Group ID',
        help="Groups related appraisals for the same employee/period"
    )
    
    related_appraisal_ids = fields.One2many(
        'hr.appraisal',
        compute='_compute_related_appraisals',
        string='Related Appraisals'
    )
    
    has_related_appraisals = fields.Boolean(
        compute='_compute_related_appraisals',
        string='Has Related Appraisals'
    )

    @api.depends('employee_id', 'appraisal_group_id')
    def _compute_related_appraisals(self):
        """Find other appraisals in the same group"""
        for record in self:
            if record.appraisal_group_id and record.employee_id:
                related = self.env['hr.appraisal'].search([
                    ('appraisal_group_id', '=', record.appraisal_group_id),
                    ('employee_id', '=', record.employee_id.id),
                    ('id', '!=', record.id)
                ])
                record.related_appraisal_ids = related
                record.has_related_appraisals = bool(related)
            else:
                record.related_appraisal_ids = False
                record.has_related_appraisals = False
    
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
        """Handle switching appraisal types - create new record if needed"""
        # Check if we're switching from a loaded type
        if self._origin.appraisal_template_type and self._origin.appraisal_template_type != self.appraisal_template_type:
            # Switching types
            if self._origin.criteria_loaded:
                # Criteria was loaded for previous type
                # We need to create a new record
                return {
                    'warning': {
                        'title': _('Create New Appraisal'),
                        'message': _(
                            'You have already loaded criteria for %s appraisal. '
                            'To create a %s appraisal, please save this record first, '
                            'then create a new appraisal from the Appraisal menu.'
                        ) % (
                            dict(self._fields['appraisal_template_type'].selection).get(self._origin.appraisal_template_type),
                            dict(self._fields['appraisal_template_type'].selection).get(self.appraisal_template_type)
                        ),
                    }
                }
        
        # Update the general criteria_loaded flag based on the selected type
        if self.appraisal_template_type == 'okr':
            self.criteria_loaded = self.okr_criteria_loaded
        elif self.appraisal_template_type == 'ninebox':
            self.criteria_loaded = self.ninebox_criteria_loaded
        elif self.appraisal_template_type == 'survey':
            self.criteria_loaded = False
        
        # Clear evaluation types when switching
        if self.appraisal_template_type != self._origin.appraisal_template_type:
            self.evaluation_type_ids = False

    def action_switch_type_and_create(self):
        """Switch type and create a new appraisal record"""
        self.ensure_one()
        
        # Save current record first
        if not self.id or isinstance(self.id, models.NewId):
            self.ensure_one()
            # Will be saved automatically
        
        # Get the target type from context
        target_type = self._context.get('target_appraisal_type')
        if not target_type:
            raise UserError(_('Target appraisal type not specified'))
        
        # Create new appraisal for the target type
        new_vals = {
            'employee_id': self.employee_id.id,
            'employee_badge_id': self.employee_badge_id.id if self.employee_badge_id else False,
            'appraisal_deadline': self.appraisal_deadline,
            'appraisal_group_id': self.appraisal_group_id or self._generate_group_id(),
            'appraisal_template_type': target_type,
            'stage_id': self.stage_id.id if self.stage_id else False,
        }
        
        new_appraisal = self.create(new_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('New %s Appraisal') % dict(self._fields['appraisal_template_type'].selection).get(target_type),
            'res_model': 'hr.appraisal',
            'res_id': new_appraisal.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _generate_group_id(self):
        """Generate a unique group ID for linking related appraisals"""
        import uuid
        return str(uuid.uuid4())
    
    def action_view_related_appraisals(self):
        """Open related appraisals in the same group"""
        self.ensure_one()
        
        related = self.env['hr.appraisal'].search([
            ('appraisal_group_id', '=', self.appraisal_group_id),
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id)
        ])
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Related Appraisals for %s') % self.employee_id.name,
            'res_model': 'hr.appraisal',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', related.ids)],
            'context': {'create': False},
        }
    
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
        if self._context.get('clear_all_templates'):
            self.okr_template_id = False
            self.ninebox_template_id = False
            self.survey_id = False
            self.evaluation_type_ids = False
            
            # Clear all criteria lines
            self.okr_line_ids.unlink()
            self.ninebox_performance_line_ids.unlink()
            self.ninebox_potential_line_ids.unlink()
            
            # Reset all criteria loaded flags
            self.criteria_loaded = False
            self.okr_criteria_loaded = False
            self.ninebox_criteria_loaded = False
            
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
        """Override create to handle badge ID lookup and ensure stage_id is set."""
        for vals in vals_list:
            if vals.get('employee_badge_id') and not vals.get('employee_id'):
                badge = self.env['employee.badge'].browse(vals['employee_badge_id'])
                if badge and badge.employee_id:
                    vals['employee_id'] = badge.employee_id.id
            # Ensure stage_id is always set to first stage if missing
            if not vals.get('stage_id'):
                first_stage = self.env['hr.appraisal.stages'].search([], limit=1, order='sequence ASC')
                if first_stage:
                    vals['stage_id'] = first_stage.id
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

    # Track which type has loaded criteria
    okr_criteria_loaded = fields.Boolean('OKR Criteria Loaded', default=False)
    ninebox_criteria_loaded = fields.Boolean('9-Box Criteria Loaded', default=False)
    
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

    # ============ PERFORMANCE CHART ============
    performance_chart_html = fields.Html(
        string='Performance Chart',
        compute='_compute_performance_chart',
        sanitize=False,
    )

    @api.depends('okr_line_ids.target_value', 'okr_line_ids.actual_value',
                 'okr_line_ids.achievement_percentage', 'okr_line_ids.line_type',
                 'okr_line_ids.weighted_score', 'okr_line_ids.weightage',
                 'ninebox_performance_line_ids.target_value', 'ninebox_performance_line_ids.actual_value',
                 'ninebox_performance_line_ids.achievement_percentage', 'ninebox_performance_line_ids.line_type',
                 'ninebox_performance_line_ids.weighted_score', 'ninebox_performance_line_ids.weightage',
                 'ninebox_potential_line_ids.target_value', 'ninebox_potential_line_ids.actual_value',
                 'ninebox_potential_line_ids.achievement_percentage', 'ninebox_potential_line_ids.line_type',
                 'ninebox_potential_line_ids.weighted_score', 'ninebox_potential_line_ids.weightage',
                 'total_performance_score', 'total_potential_score',
                 'appraisal_template_type', 'criteria_loaded')
    def _compute_performance_chart(self):
        """Generate HTML performance chart - different for OKR vs 9-Box."""
        for record in self:
            if not record.criteria_loaded or record.appraisal_template_type == 'survey':
                record.performance_chart_html = False
                continue

            if record.appraisal_template_type == 'okr':
                record.performance_chart_html = record._build_okr_chart_html()
            elif record.appraisal_template_type == 'ninebox':
                record.performance_chart_html = record._build_ninebox_chart_html()
            else:
                record.performance_chart_html = False

    def _get_rating(self, pct):
        """Get rating label and color based on percentage."""
        if pct >= 90:
            return 'Outstanding', '#2E7D32'
        elif pct >= 75:
            return 'Exceeds Expectations', '#1565C0'
        elif pct >= 60:
            return 'Meets Expectations', '#6A1B9A'
        elif pct >= 40:
            return 'Needs Improvement', '#E65100'
        else:
            return 'Unsatisfactory', '#C62828'

    def _build_donut_svg(self, pct, color, size=140):
        """Build SVG donut ring for a percentage value."""
        half = size / 2
        radius = half - 16
        stroke = 10
        circumference = 2 * 3.14159 * radius
        dash = circumference * min(pct, 100) / 100
        gap = circumference - dash
        return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
            <circle cx="{half}" cy="{half}" r="{radius}" fill="none" stroke="#E8E8E8" stroke-width="{stroke}"/>
            <circle cx="{half}" cy="{half}" r="{radius}" fill="none" stroke="{color}" stroke-width="{stroke}"
                    stroke-dasharray="{dash:.1f} {gap:.1f}" stroke-linecap="round"
                    transform="rotate(-90 {half} {half})" style="transition: stroke-dasharray 0.6s;"/>
            <text x="{half}" y="{half - 6}" text-anchor="middle" font-size="22" font-weight="700" fill="{color}">{pct:.0f}%</text>
            <text x="{half}" y="{half + 12}" text-anchor="middle" font-size="9" fill="#888">Achievement</text>
        </svg>'''

    # ============ OKR PERFORMANCE CHART ============
    def _build_okr_chart_html(self):
        """Build OKR-specific performance chart with clear progress bars."""
        self.ensure_one()
        groups = {}
        palette = {'Department': '#4A90E2', 'Role': '#26A69A', 'Common': '#AB47BC'}

        for line in self.okr_line_ids:
            lbl = dict(line._fields['line_type'].selection).get(line.line_type, 'Other')
            grp = groups.setdefault(lbl, {'target': 0, 'actual': 0, 'count': 0, 'weighted_score': 0, 'weightage': 0})
            grp['target'] += line.target_value
            grp['actual'] += line.actual_value
            grp['count'] += 1
            grp['weighted_score'] += line.weighted_score
            grp['weightage'] += line.weightage

        if not groups:
            return '<p class="text-muted">No criteria data to display.</p>'

        total_target = sum(g['target'] for g in groups.values())
        total_actual = sum(g['actual'] for g in groups.values())
        overall_pct = (total_actual / total_target * 100) if total_target > 0 else 0
        total_weighted = sum(g['weighted_score'] for g in groups.values())
        r_label, r_color = self._get_rating(overall_pct)

        donut_svg = self._build_donut_svg(overall_pct, r_color)

        # Build category cards
        cards_html = ''
        for grp_name, gdata in groups.items():
            color = palette.get(grp_name, '#4A90E2')
            ach = (gdata['actual'] / gdata['target'] * 100) if gdata['target'] > 0 else 0
            cards_html += f'''
            <div style="flex:1; min-width:160px; max-width:250px; background:#FAFAFA; border-radius:8px; padding:12px 14px; border-top:3px solid {color};">
                <div style="font-size:11px; color:#888; font-weight:600; text-transform:uppercase; margin-bottom:4px;">{grp_name}</div>
                <div style="font-size:22px; font-weight:700; color:{color};">{ach:.0f}<span style="font-size:13px;">%</span></div>
                <div style="font-size:10px; color:#999; margin-top:2px;">
                    {gdata['count']} criteria &middot; Target {gdata['target']:.0f} &middot; Actual {gdata['actual']:.0f}
                </div>
            </div>'''

        # Build horizontal progress bars per category
        bars_html = ''
        for grp_name, gdata in groups.items():
            color = palette.get(grp_name, '#4A90E2')
            ach = (gdata['actual'] / gdata['target'] * 100) if gdata['target'] > 0 else 0
            fill_pct = min(ach, 100)
            overflow = ach > 100
            ach_label, ach_color = self._get_rating(ach)

            # Target / Actual annotation
            target_txt = f"{gdata['target']:.0f}"
            actual_txt = f"{gdata['actual']:.0f}"

            bars_html += f'''
            <div style="margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
                    <span style="font-size:12px; font-weight:600; color:#333;">{grp_name}</span>
                    <span style="font-size:11px; color:#666;">
                        Actual <strong style="color:{color};">{actual_txt}</strong> / Target <strong>{target_txt}</strong>
                    </span>
                </div>
                <div style="position:relative; background:#E8E8E8; border-radius:6px; height:28px; overflow:visible;">
                    <div style="position:absolute; top:0; left:0; height:100%; width:{fill_pct:.1f}%; background:{color};
                                border-radius:6px; transition:width 0.4s;{' box-shadow: 0 0 8px ' + color + ';' if overflow else ''}"></div>
                    <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; align-items:center;
                                justify-content:flex-end; padding-right:10px;">
                        <span style="font-size:13px; font-weight:700; color:{ach_color}; text-shadow:0 0 3px rgba(255,255,255,0.8);">
                            {ach:.1f}%
                        </span>
                    </div>
                </div>
                <!-- Weighted Score field is hidden
                <div style="font-size:10px; color:#999; margin-top:2px;">
                    Weighted Score: [value hidden]
                </div>
                -->
            </div>'''

        return f'''
        <div style="font-family: 'Segoe UI', system-ui, sans-serif;">
            <div style="display:flex; align-items:center; gap:24px; margin-bottom:18px; flex-wrap:wrap;">
                <div style="text-align:center;">{donut_svg}</div>
                <div style="min-width:180px;">
                    <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.5px;">
                        Performance Rating
                        <span title="Rating is determined by the Overall Achievement %:&#10;&#10;  ≥ 90%  →  Outstanding&#10;  ≥ 75%  →  Exceeds Expectations&#10;  ≥ 60%  →  Meets Expectations&#10;  ≥ 40%  →  Needs Improvement&#10;  &lt; 40%  →  Unsatisfactory&#10;&#10;Overall Achievement % = (Total Actual × 100) / Total Target"
                              style="cursor:help; display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; border-radius:50%; background:#E0E0E0; color:#666; font-size:9px; font-weight:700; margin-left:3px; vertical-align:middle;">?</span>
                    </div>
                    <div style="font-size:20px; font-weight:800; color:{r_color}; margin:4px 0;">{r_label}</div>
                    <!-- Weighted Score field is hidden
                    <div style="font-size:12px; color:#666;">
                        Weighted Score: [value hidden]
                    </div>
                    -->
                    <div style="font-size:12px; color:#666;">
                        Total: <strong style="color:#4A90E2;">{total_target:.0f}</strong>
                        <span style="color:#bbb;"> / </span>
                        <strong style="color:#26A69A;">{total_actual:.0f}</strong>
                        <span title="Displays: Total Target / Total Actual&#10;&#10;Achievement % = (Actual × 100) / Target&#10;= ({total_actual:.0f} × 100) / {total_target:.0f}&#10;= {overall_pct:.1f}%"
                              style="cursor:help; display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px; border-radius:50%; background:#E0E0E0; color:#666; font-size:10px; font-weight:700; margin-left:4px; vertical-align:middle;">?</span>
                    </div>
                </div>
                <div style="display:flex; gap:10px; flex-wrap:wrap; flex:1;">{cards_html}</div>
            </div>
            <div style="background:#FAFAFA; border:1px solid #EEE; border-radius:10px; padding:18px 16px 8px 16px;">
                <div style="font-size:13px; font-weight:600; color:#555; margin-bottom:14px;">Achievement by Category</div>
                {bars_html}
            </div>
        </div>'''

    # ============ 9-BOX GRID PERFORMANCE CHART ============
    def _build_ninebox_chart_html(self):
        """Build professional 9-Box Grid visualization for Performance Summary."""
        self.ensure_one()

        perf_score = self.total_performance_score
        pot_score = self.total_potential_score
        perf_pct = min(perf_score, 100)
        pot_pct = min(pot_score, 100)

        # Determine quadrant
        def _quad(p):
            if p >= 66.67:
                return 2  # High
            elif p >= 33.33:
                return 1  # Medium
            return 0  # Low

        perf_q = _quad(perf_pct)
        pot_q = _quad(pot_pct)

        # 9-box definitions [row_from_top][col_from_left]
        # row 0 = High Potential (top), row 2 = Low Potential (bottom)
        # col 0 = Low Performance (left), col 2 = High Performance (right)
        cells = [
            # Row 0: High Potential
            [
                {'name': 'Enigma', 'sub': 'Rough Diamond', 'bg': '#FFF3E0', 'border': '#FFB74D', 'icon': '&#x1F48E;'},
                {'name': 'Growth Gem', 'sub': 'High Impact', 'bg': '#E8F5E9', 'border': '#81C784', 'icon': '&#x1F331;'},
                {'name': 'Star', 'sub': 'Top Talent', 'bg': '#E8F5E9', 'border': '#4CAF50', 'icon': '&#x2B50;'},
            ],
            # Row 1: Medium Potential
            [
                {'name': 'Dilemma', 'sub': 'Up or Out', 'bg': '#FFF3E0', 'border': '#FF8A65', 'icon': '&#x26A0;'},
                {'name': 'Core Player', 'sub': 'Key Contributor', 'bg': '#FFFDE7', 'border': '#FFD54F', 'icon': '&#x1F3AF;'},
                {'name': 'High Performer', 'sub': 'Future Star', 'bg': '#E8F5E9', 'border': '#66BB6A', 'icon': '&#x1F680;'},
            ],
            # Row 2: Low Potential
            [
                {'name': 'Talent Risk', 'sub': 'Underperformer', 'bg': '#FFEBEE', 'border': '#EF5350', 'icon': '&#x1F6A8;'},
                {'name': 'Average', 'sub': 'Solid Performer', 'bg': '#FFF8E1', 'border': '#FFB74D', 'icon': '&#x1F4BC;'},
                {'name': 'Workhorse', 'sub': 'Trusted Pro', 'bg': '#E3F2FD', 'border': '#42A5F5', 'icon': '&#x1F3C6;'},
            ],
        ]

        # Employee's cell: pot_q=2 -> row 0, pot_q=0 -> row 2
        emp_row = 2 - pot_q
        emp_col = perf_q
        emp_cell = cells[emp_row][emp_col]

        # Grid SVG dimensions - large for clear visibility
        grid_w, grid_h = 660, 480
        margin_l, margin_t, margin_r, margin_b = 70, 35, 15, 50
        cell_w = grid_w / 3
        cell_h = grid_h / 3

        # Pot/Perf labels
        pot_labels = ['Low', 'Medium', 'High']
        perf_labels = ['Low', 'Medium', 'High']

        # Build grid SVG
        svg_total_w = margin_l + grid_w + margin_r
        svg_total_h = margin_t + grid_h + margin_b
        svg = f'<svg width="{svg_total_w}" height="{svg_total_h}" viewBox="0 0 {svg_total_w} {svg_total_h}" style="font-family: Segoe UI, system-ui, sans-serif;">'

        # Draw cells
        for row in range(3):
            for col in range(3):
                cx = margin_l + col * cell_w
                cy = margin_t + row * cell_h
                cell = cells[row][col]
                is_active = (row == emp_row and col == emp_col)
                stroke_w = 3 if is_active else 1
                stroke_c = cell['border'] if is_active else '#DDD'
                opacity = '1' if is_active else '0.6'

                svg += f'<rect x="{cx}" y="{cy}" width="{cell_w}" height="{cell_h}" rx="6" fill="{cell["bg"]}" stroke="{stroke_c}" stroke-width="{stroke_w}" opacity="{opacity}"/>'
                # Icon
                svg += f'<text x="{cx + cell_w/2}" y="{cy + 38}" text-anchor="middle" font-size="26">{cell["icon"]}</text>'
                # Name
                font_w = '700' if is_active else '600'
                f_size = '14' if is_active else '12'
                svg += f'<text x="{cx + cell_w/2}" y="{cy + 66}" text-anchor="middle" font-size="{f_size}" font-weight="{font_w}" fill="#333">{cell["name"]}</text>'
                # Subtitle
                svg += f'<text x="{cx + cell_w/2}" y="{cy + 86}" text-anchor="middle" font-size="10" fill="#888">{cell["sub"]}</text>'

                # Active cell highlight
                if is_active:
                    svg += f'<rect x="{cx + 2}" y="{cy + 2}" width="{cell_w - 4}" height="{cell_h - 4}" rx="5" fill="none" stroke="{cell["border"]}" stroke-width="2" stroke-dasharray="6 3" opacity="0.5"/>'

        # Employee position dot (precise based on scores)
        dot_x = margin_l + (perf_pct / 100) * grid_w
        dot_y = margin_t + (1 - pot_pct / 100) * grid_h
        # Clamp within grid
        dot_x = max(margin_l + 10, min(dot_x, margin_l + grid_w - 10))
        dot_y = max(margin_t + 10, min(dot_y, margin_t + grid_h - 10))

        svg += f'''
            <circle cx="{dot_x}" cy="{dot_y}" r="16" fill="{emp_cell["border"]}" opacity="0.3"/>
            <circle cx="{dot_x}" cy="{dot_y}" r="10" fill="{emp_cell["border"]}" stroke="white" stroke-width="3"/>
            <circle cx="{dot_x}" cy="{dot_y}" r="4" fill="white"/>
        '''

        # Y-axis label (Potential)
        svg += f'<text x="18" y="{margin_t + grid_h/2}" text-anchor="middle" font-size="13" font-weight="700" fill="#555" transform="rotate(-90 18 {margin_t + grid_h/2})">POTENTIAL &#x2192;</text>'
        for i, lbl in enumerate(reversed(pot_labels)):
            y_center = margin_t + i * cell_h + cell_h / 2
            svg += f'<text x="{margin_l - 10}" y="{y_center + 4}" text-anchor="end" font-size="11" fill="#999">{lbl}</text>'

        # X-axis label (Performance)
        svg += f'<text x="{margin_l + grid_w/2}" y="{margin_t + grid_h + 45}" text-anchor="middle" font-size="13" font-weight="700" fill="#555">PERFORMANCE &#x2192;</text>'
        for i, lbl in enumerate(perf_labels):
            x_center = margin_l + i * cell_w + cell_w / 2
            svg += f'<text x="{x_center}" y="{margin_t + grid_h + 22}" text-anchor="middle" font-size="11" fill="#999">{lbl}</text>'

        svg += '</svg>'

        # Build score gauges
        def _mini_gauge(label, score, color):
            pct = min(score, 100)
            return f'''
            <div style="text-align:center; min-width:100px;">
                <div style="font-size:10px; font-weight:600; color:#888; text-transform:uppercase; letter-spacing:0.3px; margin-bottom:6px;">{label}</div>
                <div style="position:relative; width:80px; height:80px; margin:0 auto;">
                    <svg width="80" height="80" viewBox="0 0 80 80">
                        <circle cx="40" cy="40" r="32" fill="none" stroke="#E8E8E8" stroke-width="7"/>
                        <circle cx="40" cy="40" r="32" fill="none" stroke="{color}" stroke-width="7"
                                stroke-dasharray="{2*3.14159*32*pct/100:.1f} {2*3.14159*32*(100-pct)/100:.1f}"
                                stroke-linecap="round" transform="rotate(-90 40 40)"/>
                        <text x="40" y="43" text-anchor="middle" font-size="16" font-weight="700" fill="{color}">{score:.0f}</text>
                    </svg>
                </div>
            </div>'''

        _, perf_color = self._get_rating(perf_pct)
        _, pot_color = self._get_rating(pot_pct)
        avg_score = (perf_pct + pot_pct) / 2
        _, overall_color = self._get_rating(avg_score)
        overall_label, _ = self._get_rating(avg_score)

        # Performance and Potential category breakdowns
        def _build_breakdown(lines, dimension_label):
            if not lines:
                return ''
            groups = {}
            for line in lines:
                lbl = dict(line._fields['line_type'].selection).get(line.line_type, 'Other')
                grp = groups.setdefault(lbl, {'target': 0, 'actual': 0, 'count': 0})
                grp['target'] += line.target_value
                grp['actual'] += line.actual_value
                grp['count'] += 1
            breakdown_html = f'<div style="font-size:10px; font-weight:600; color:#888; text-transform:uppercase; margin-bottom:6px;">{dimension_label} Breakdown</div>'
            for lbl, d in groups.items():
                ach = (d['actual'] / d['target'] * 100) if d['target'] > 0 else 0
                _, c = self._get_rating(ach)
                breakdown_html += f'''
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                    <span style="font-size:11px; min-width:75px; color:#555;">{lbl}</span>
                    <div style="flex:1; background:#E8E8E8; border-radius:3px; height:8px; overflow:hidden;">
                        <div style="height:100%; width:{min(ach, 100):.1f}%; background:{c}; border-radius:3px;"></div>
                    </div>
                    <span style="font-size:11px; font-weight:600; color:{c}; min-width:40px; text-align:right;">{ach:.0f}%</span>
                </div>'''
            return breakdown_html

        perf_breakdown = _build_breakdown(self.ninebox_performance_line_ids, 'Performance')
        pot_breakdown = _build_breakdown(self.ninebox_potential_line_ids, 'Potential')

        return f'''
        <div style="font-family: 'Segoe UI', system-ui, sans-serif;">
            <!-- Top: Quadrant badge + Score gauges -->
            <div style="display:flex; align-items:center; gap:20px; margin-bottom:18px; flex-wrap:wrap;">
                <!-- Quadrant badge -->
                <div style="background:{emp_cell['bg']}; border:2px solid {emp_cell['border']}; border-radius:12px; padding:14px 20px; text-align:center; min-width:170px;">
                    <div style="font-size:24px; margin-bottom:4px;">{emp_cell['icon']}</div>
                    <div style="font-size:16px; font-weight:800; color:#333;">{emp_cell['name']}</div>
                    <div style="font-size:11px; color:#888; margin-top:2px;">{emp_cell['sub']}</div>
                    <div style="font-size:11px; font-weight:600; color:{overall_color}; margin-top:6px;">{overall_label}</div>
                </div>
                <!-- Score gauges -->
                {_mini_gauge('Performance', perf_score, perf_color)}
                {_mini_gauge('Potential', pot_score, pot_color)}
                <!-- Breakdowns -->
                <div style="flex:1; min-width:200px;">
                    <div style="margin-bottom:10px;">{perf_breakdown}</div>
                    <div>{pot_breakdown}</div>
                </div>
            </div>

            <!-- 9-Box Grid -->
            <div style="background:#FAFAFA; border:1px solid #EEE; border-radius:10px; padding:16px; overflow-x:auto;">
                <div style="font-size:13px; font-weight:600; color:#555; margin-bottom:10px;">9-Box Grid Position</div>
                {svg}
                <div style="margin-top:8px; display:flex; align-items:center; gap:8px; font-size:10px; color:#888;">
                    <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{emp_cell['border']};"></span>
                    Employee Position (Performance: {perf_score:.1f}, Potential: {pot_score:.1f})
                </div>
            </div>
        </div>'''

    # Add these compute methods
    
    @api.depends('okr_line_ids.weighted_score', 'okr_line_ids.weightage',
                 'ninebox_performance_line_ids.weighted_score', 'ninebox_performance_line_ids.weightage',
                 'ninebox_potential_line_ids.weighted_score', 'ninebox_potential_line_ids.weightage')
    def _compute_total_scores(self):
        """Calculate total scores as weighted average percentages (0-100 scale).
        
        Formula: total = sum(weighted_score) / sum(weightage) * 100
        where weighted_score = (achievement% / 100) * weightage for each line.
        This gives a proper 0-100% weighted average achievement.
        """
        for record in self:
            # OKR
            okr_ws = sum(record.okr_line_ids.mapped('weighted_score'))
            okr_wt = sum(record.okr_line_ids.mapped('weightage'))
            record.total_okr_score = (okr_ws / okr_wt * 100) if okr_wt > 0 else 0.0
            
            # Performance
            perf_ws = sum(record.ninebox_performance_line_ids.mapped('weighted_score'))
            perf_wt = sum(record.ninebox_performance_line_ids.mapped('weightage'))
            record.total_performance_score = (perf_ws / perf_wt * 100) if perf_wt > 0 else 0.0
            
            # Potential
            pot_ws = sum(record.ninebox_potential_line_ids.mapped('weighted_score'))
            pot_wt = sum(record.ninebox_potential_line_ids.mapped('weightage'))
            record.total_potential_score = (pot_ws / pot_wt * 100) if pot_wt > 0 else 0.0
    
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
        """Load criteria from selected template and auto-save/reload the record"""
        self.ensure_one()
        
        if not self.employee_id:
            raise UserError(_('Please select an employee first.'))
        
        if not self.evaluation_type_ids:
            raise UserError(_('Please select at least one Evaluation Type.'))
        
        if self.appraisal_template_type == 'okr' and self.okr_template_id:
            self._load_okr_criteria()
            self.okr_criteria_loaded = True
        elif self.appraisal_template_type == 'ninebox' and self.ninebox_template_id:
            self._load_ninebox_criteria()
            self.ninebox_criteria_loaded = True
        else:
            raise UserError(_('Please select a template first.'))
        
        self.criteria_loaded = True
        
        # Generate appraisal group ID if not exists
        if not self.appraisal_group_id:
            import uuid
            self.appraisal_group_id = str(uuid.uuid4())
        
        # Force save the record (this commits the changes to database)
        if self.id and not isinstance(self.id, models.NewId):
            # Existing record - just reload
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        else:
            # New record - the record will be auto-saved when method completes
            # Just return reload action
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
    
    def action_create_new_type_appraisal(self):
        """Create a new appraisal record when switching types after loading"""
        self.ensure_one()
        
        if not self.criteria_loaded:
            # No criteria loaded yet, just switch type normally
            return
        
        # Criteria already loaded, need to create new record
        new_vals = {
            'employee_id': self.employee_id.id,
            'employee_badge_id': self.employee_badge_id.id if self.employee_badge_id else False,
            'appraisal_deadline': self.appraisal_deadline,
            'appraisal_group_id': self.appraisal_group_id,  # Link to same group
            'appraisal_template_type': self.appraisal_template_type,
            'stage_id': self.stage_id.id if self.stage_id else False,
        }
        
        new_appraisal = self.create(new_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Appraisal'),
            'res_model': 'hr.appraisal',
            'res_id': new_appraisal.id,
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'current',
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
        """Clear criteria when evaluation types change after loading"""
        if self.criteria_loaded and self._origin.evaluation_type_ids:
            # If criteria were already loaded and evaluation types changed
            # Clear the loaded criteria for current type
            if self.appraisal_template_type == 'okr':
                self.okr_line_ids.unlink()
                self.okr_criteria_loaded = False
            elif self.appraisal_template_type == 'ninebox':
                self.ninebox_performance_line_ids.unlink()
                self.ninebox_potential_line_ids.unlink()
                self.ninebox_criteria_loaded = False
            
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
        """Generate spreadsheet for OKR criteria with formulas and read-only styling.
        Only column G (Actual) is editable — all others use locked styling.
        Achievement % (H) uses a live formula.
        """
        cells = {}
        headers = ['Seq', 'Type', 'Objective', 'Priority', 'Metric', 'Target', 'Actual', 'Achievement %', 'Weightage %', 'Team']

        # Style IDs:
        # 1 = Header (blue)
        # 2 = Totals (green)
        # 3 = Locked cell (light grey background) — non-editable visual cue
        # 4 = Editable cell (white background) — Actual column
        # 5 = Formula cell (light blue background)

        # Header row
        for col_idx, header in enumerate(headers):
            col_letter = self._number_to_column(col_idx)
            cells[f'{col_letter}1'] = {'content': header, 'style': 1}

        # Data rows
        lines = self.okr_line_ids.sorted('sequence')
        for row_idx, line in enumerate(lines, start=2):
            # A: Seq (locked)
            cells[f'A{row_idx}'] = {'content': str(line.sequence), 'style': 3}
            # B: Type (locked)
            cells[f'B{row_idx}'] = {'content': str(dict(line._fields['line_type'].selection).get(line.line_type, '')), 'style': 3}
            # C: Objective (locked)
            cells[f'C{row_idx}'] = {'content': str(line.objective_breakdown or ''), 'style': 3}
            # D: Priority (locked)
            cells[f'D{row_idx}'] = {'content': str(dict(line._fields['priority'].selection).get(line.priority, '') if line.priority else ''), 'style': 3}
            # E: Metric (locked)
            cells[f'E{row_idx}'] = {'content': str(dict(line._fields['metric'].selection).get(line.metric, '') if line.metric else ''), 'style': 3}
            # F: Target (locked)
            cells[f'F{row_idx}'] = {'content': str(round(line.target_value, 2)), 'style': 3, 'format': 1}
            # G: Actual (EDITABLE — the only editable column)
            cells[f'G{row_idx}'] = {'content': str(round(line.actual_value, 2)), 'style': 4, 'format': 1}
            # H: Achievement % = IF(F>0, G/F*100, 0) — FORMULA
            cells[f'H{row_idx}'] = {'content': f'=IF(F{row_idx}>0, G{row_idx}/F{row_idx}*100, 0)', 'style': 5, 'format': 1}
            # I: Weightage (locked)
            cells[f'I{row_idx}'] = {'content': str(round(line.weightage, 2)), 'style': 3, 'format': 1}
            # J: Team (locked)
            cells[f'J{row_idx}'] = {'content': str(line.team_id.name if line.team_id else ''), 'style': 3}

        # Totals row with SUM formulas
        total_row = len(lines) + 2
        last_data_row = total_row - 1
        cells[f'A{total_row}'] = {'content': 'TOTALS:', 'style': 2}
        cells[f'F{total_row}'] = {'content': f'=SUM(F2:F{last_data_row})', 'style': 2, 'format': 1}
        cells[f'G{total_row}'] = {'content': f'=SUM(G2:G{last_data_row})', 'style': 2, 'format': 1}
        cells[f'I{total_row}'] = {'content': f'=SUM(I2:I{last_data_row})', 'style': 2, 'format': 1}

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
                '2': {'bold': True, 'fillColor': '#E8F5E9'},
                '3': {'fillColor': '#F5F5F5', 'textColor': '#555555'},
                '4': {'fillColor': '#FFFFFF', 'bold': True},
                '5': {'fillColor': '#E3F2FD', 'textColor': '#1565C0', 'italic': True},
            },
            'formats': {'1': '#,##0.00'},
            'borders': {},
            'settings': {'locale': locale},
            'revisionId': 'START_REVISION',
        }
    
    def _generate_ninebox_spreadsheet(self, locale):
        """Generate spreadsheet for 9-Box criteria with formulas and read-only styling.
        Only column G (Actual) is editable — all others use locked styling.
        Achievement % (H) uses a live formula.
        """
        sheets = []
        headers = ['Seq', 'Type', 'Objective', 'Priority', 'Metric', 'Target', 'Actual', 'Achievement %', 'Weightage %', 'Team']

        def _generate_sheet_cells(line_records, header_style, totals_style):
            """Helper to generate cells for a single sheet with formulas."""
            sheet_cells = {}
            # Header row
            for col_idx, header in enumerate(headers):
                col_letter = self._number_to_column(col_idx)
                sheet_cells[f'{col_letter}1'] = {'content': header, 'style': header_style}

            # Data rows
            sorted_lines = line_records.sorted('sequence')
            for row_idx, line in enumerate(sorted_lines, start=2):
                sheet_cells[f'A{row_idx}'] = {'content': str(line.sequence), 'style': 7}
                sheet_cells[f'B{row_idx}'] = {'content': str(dict(line._fields['line_type'].selection).get(line.line_type, '')), 'style': 7}
                sheet_cells[f'C{row_idx}'] = {'content': str(line.objective_breakdown or ''), 'style': 7}
                sheet_cells[f'D{row_idx}'] = {'content': str(dict(line._fields['priority'].selection).get(line.priority, '') if line.priority else ''), 'style': 7}
                sheet_cells[f'E{row_idx}'] = {'content': str(dict(line._fields['metric'].selection).get(line.metric, '') if line.metric else ''), 'style': 7}
                sheet_cells[f'F{row_idx}'] = {'content': str(round(line.target_value, 2)), 'style': 7, 'format': 1}
                # G: Actual (EDITABLE)
                sheet_cells[f'G{row_idx}'] = {'content': str(round(line.actual_value, 2)), 'style': 8, 'format': 1}
                # H: Achievement % — FORMULA
                sheet_cells[f'H{row_idx}'] = {'content': f'=IF(F{row_idx}>0, G{row_idx}/F{row_idx}*100, 0)', 'style': 9, 'format': 1}
                sheet_cells[f'I{row_idx}'] = {'content': str(round(line.weightage, 2)), 'style': 7, 'format': 1}
                # J: Team (locked)
                sheet_cells[f'J{row_idx}'] = {'content': str(line.team_id.name if line.team_id else ''), 'style': 7}

            # Totals
            total_row = len(sorted_lines) + 2
            last_data_row = total_row - 1
            sheet_cells[f'A{total_row}'] = {'content': 'TOTALS:', 'style': totals_style}
            sheet_cells[f'F{total_row}'] = {'content': f'=SUM(F2:F{last_data_row})', 'style': totals_style, 'format': 1}
            sheet_cells[f'G{total_row}'] = {'content': f'=SUM(G2:G{last_data_row})', 'style': totals_style, 'format': 1}
            sheet_cells[f'I{total_row}'] = {'content': f'=SUM(I2:I{last_data_row})', 'style': totals_style, 'format': 1}

            return sheet_cells, total_row

        # Performance Sheet
        if self.ninebox_performance_line_ids:
            perf_cells, perf_total_row = _generate_sheet_cells(
                self.ninebox_performance_line_ids, header_style=3, totals_style=4
            )
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
            pot_cells, pot_total_row = _generate_sheet_cells(
                self.ninebox_potential_line_ids, header_style=5, totals_style=6
            )
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
                '7': {'fillColor': '#F5F5F5', 'textColor': '#555555'},
                '8': {'fillColor': '#FFFFFF', 'bold': True},
                '9': {'fillColor': '#E3F2FD', 'textColor': '#1565C0', 'italic': True},
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

    # ============ BIDIRECTIONAL SYNC: CRITERIA <-> SPREADSHEET ============

    def _sync_criteria_to_spreadsheet(self):
        """Regenerate spreadsheet data from current criteria lines.
        Called automatically when actual_value changes on any criteria line.
        """
        self.ensure_one()
        if not self.spreadsheet_id or not self.criteria_loaded:
            return

        import json
        import base64

        # Get locale
        lang = self.env['res.lang']._lang_get(self.env.user.lang)
        locale = lang._odoo_lang_to_spreadsheet_locale()

        # Regenerate spreadsheet data based on template type
        if self.appraisal_template_type == 'okr':
            spreadsheet_data = self._generate_okr_spreadsheet(locale)
        elif self.appraisal_template_type == 'ninebox':
            spreadsheet_data = self._generate_ninebox_spreadsheet(locale)
        else:
            return

        # Update spreadsheet (this clears revisions via spreadsheet.abstract write)
        self.spreadsheet_id.spreadsheet_raw = spreadsheet_data
        _logger.info("Synced criteria to spreadsheet for appraisal %s", self.id)

    def _sync_spreadsheet_to_criteria(self):
        """Read actual values from spreadsheet and update criteria lines.
        Parses the spreadsheet JSON to extract 'Actual' column values
        and writes them back to the corresponding OKR/9-Box criteria lines.
        """
        self.ensure_one()
        if not self.spreadsheet_id or not self.criteria_loaded:
            raise UserError(_('No spreadsheet or criteria loaded to sync.'))

        data = self.spreadsheet_id.spreadsheet_raw
        if not data or not data.get('sheets'):
            raise UserError(_('Spreadsheet contains no data.'))

        if self.appraisal_template_type == 'okr':
            self._sync_okr_from_spreadsheet(data)
        elif self.appraisal_template_type == 'ninebox':
            self._sync_ninebox_from_spreadsheet(data)

        _logger.info("Synced spreadsheet to criteria for appraisal %s", self.id)

    def _sync_okr_from_spreadsheet(self, data):
        """Parse OKR spreadsheet and update okr_line_ids actual values.
        Spreadsheet columns: A=Seq, B=Type, C=Objective, D=Priority, E=Metric,
                             F=Target, G=Actual, H=Achievement%, I=Weightage%, J=WeightedScore, K=Team
        """
        sheet = data['sheets'][0] if data.get('sheets') else None
        if not sheet:
            return

        cells = sheet.get('cells', {})
        lines = self.okr_line_ids.sorted('sequence')

        for row_idx, line in enumerate(lines, start=2):
            actual_cell_ref = f'G{row_idx}'
            cell = cells.get(actual_cell_ref, {})
            actual_str = cell.get('content', '0')
            try:
                actual_val = float(actual_str)
            except (ValueError, TypeError):
                actual_val = 0.0

            if abs(line.actual_value - actual_val) > 0.001:
                line.with_context(skip_spreadsheet_sync=True).write({
                    'actual_value': actual_val
                })

    def _sync_ninebox_from_spreadsheet(self, data):
        """Parse 9-Box spreadsheet (2 sheets: Performance + Potential)
        and update ninebox lines actual values.
        Columns: A=Seq, B=Type, C=Objective, D=Priority, E=Metric,
                 F=Target, G=Actual, H=Achievement%, I=Weightage%, J=WeightedScore, K=Team
        """
        sheets = data.get('sheets', [])

        # Performance sheet (first sheet)
        perf_sheet = next((s for s in sheets if 'erformance' in s.get('name', '')), None)
        if perf_sheet:
            cells = perf_sheet.get('cells', {})
            perf_lines = self.ninebox_performance_line_ids.sorted('sequence')
            for row_idx, line in enumerate(perf_lines, start=2):
                actual_cell_ref = f'G{row_idx}'
                cell = cells.get(actual_cell_ref, {})
                actual_str = cell.get('content', '0')
                try:
                    actual_val = float(actual_str)
                except (ValueError, TypeError):
                    actual_val = 0.0
                if abs(line.actual_value - actual_val) > 0.001:
                    line.with_context(skip_spreadsheet_sync=True).write({
                        'actual_value': actual_val
                    })

        # Potential sheet (second sheet)
        pot_sheet = next((s for s in sheets if 'otential' in s.get('name', '')), None)
        if pot_sheet:
            cells = pot_sheet.get('cells', {})
            pot_lines = self.ninebox_potential_line_ids.sorted('sequence')
            for row_idx, line in enumerate(pot_lines, start=2):
                actual_cell_ref = f'G{row_idx}'
                cell = cells.get(actual_cell_ref, {})
                actual_str = cell.get('content', '0')
                try:
                    actual_val = float(actual_str)
                except (ValueError, TypeError):
                    actual_val = 0.0
                if abs(line.actual_value - actual_val) > 0.001:
                    line.with_context(skip_spreadsheet_sync=True).write({
                        'actual_value': actual_val
                    })

    def action_refresh_spreadsheet(self):
        """Refresh button action: Bidirectional sync between spreadsheet and criteria.
        1. First sync FROM spreadsheet → criteria (get latest edits from spreadsheet)
        2. Then sync FROM criteria → spreadsheet (regenerate with computed scores)
        This ensures both sides are fully in sync.
        """
        self.ensure_one()
        if not self.spreadsheet_id:
            raise UserError(_('No spreadsheet found. Please generate a spreadsheet first.'))
        if not self.criteria_loaded:
            raise UserError(_('No criteria loaded to refresh.'))

        # Step 1: Pull latest values from spreadsheet into criteria lines
        self._sync_spreadsheet_to_criteria()

        # Step 2: Regenerate spreadsheet with updated computed fields (achievement%, weighted score)
        self._sync_criteria_to_spreadsheet()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Spreadsheet Refreshed'),
                'message': _('Criteria and spreadsheet data have been synchronized successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }