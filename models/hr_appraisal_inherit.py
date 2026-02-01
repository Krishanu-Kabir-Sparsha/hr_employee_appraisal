# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrAppraisalInherit(models.Model):
    """
    Inherit hr.appraisal from oh_appraisal to add:
    1. Badge ID field for quick employee lookup
    2. OKR/9-Box template selection
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

    # ============ BADGE ID SELECTION (Many2one to employee.badge view) ============
    employee_badge_id = fields.Many2one(
        'employee.badge',
        string='Employee Badge ID',
        help="Select employee by Badge ID - supports Search More and type to filter"
    )
    
    # ============ TEMPLATE SELECTION ============
    appraisal_template_type = fields.Selection([
        ('survey', 'Survey Form'),
        ('okr', 'OKR Template'),
        ('ninebox', '9-Box Grid Template')
    ], string='Appraisal Type', default='survey',
       help="Select the type of appraisal template to use")
    
    okr_template_id = fields.Many2one(
        'oh.appraisal.okr.template',
        string='OKR Template',
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
        help="Select an OKR template for this appraisal"
    )
    
    ninebox_template_id = fields.Many2one(
        'oh.appraisal.ninebox.template',
        string='9-Box Template',
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
        help="Select a 9-Box Grid template for this appraisal"
    )
    
    # Display field for selected template name
    selected_template_display = fields.Char(
        string='Selected Template',
        compute='_compute_selected_template_display',
        store=True
    )
    
    # ============ ONCHANGE METHODS ============
    @api.onchange('employee_badge_id')
    def _onchange_employee_badge_id(self):
        """Auto-select employee when Badge ID is selected from dropdown"""
        if self.employee_badge_id and self.employee_badge_id.employee_id:
            self.employee_id = self.employee_badge_id.employee_id.id
            # Auto-detect department and set template domain
            self._auto_detect_templates()
        elif not self.employee_badge_id:
            if not self.employee_id:
                self.employee_id = False
    
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
        
        # Auto-detect available templates for this employee
        self._auto_detect_templates()
    
    @api.onchange('appraisal_template_type')
    def _onchange_appraisal_template_type(self):
        """Clear template selections when type changes"""
        if self.appraisal_template_type == 'survey':
            self.okr_template_id = False
            self.ninebox_template_id = False
        elif self.appraisal_template_type == 'okr':
            self.ninebox_template_id = False
        elif self.appraisal_template_type == 'ninebox':
            self.okr_template_id = False
    
    @api.onchange('okr_template_id')
    def _onchange_okr_template(self):
        """Update template type when OKR template selected"""
        if self.okr_template_id:
            self.appraisal_template_type = 'okr'
            self.ninebox_template_id = False
    
    @api.onchange('ninebox_template_id')
    def _onchange_ninebox_template(self):
        """Update template type when 9-Box template selected"""
        if self.ninebox_template_id:
            self.appraisal_template_type = 'ninebox'
            self.okr_template_id = False
    
    # ============ COMPUTE METHODS ============
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
    
    # ============ HELPER METHODS ============
    def _auto_detect_templates(self):
        """Auto-detect available templates based on employee's department"""
        if self.employee_id and self.employee_id.department_id:
            dept_id = self.employee_id.department_id.id
            
            # Check for OKR templates in employee's department
            okr_template = self.env['oh.appraisal.okr.template'].search([
                ('department_id', '=', dept_id),
                ('active', '=', True)
            ], limit=1)
            
            # Check for 9-Box templates in employee's department
            ninebox_template = self.env['oh.appraisal.ninebox.template'].search([
                ('department_id', '=', dept_id),
                ('active', '=', True)
            ], limit=1)
            
            # Auto-select if only one type is available
            if okr_template and not ninebox_template:
                self.okr_template_id = okr_template.id
                self.appraisal_template_type = 'okr'
            elif ninebox_template and not okr_template:
                self.ninebox_template_id = ninebox_template.id
                self.appraisal_template_type = 'ninebox'
    
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