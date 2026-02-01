# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class EmployeeBadge(models.Model):
    """
    Virtual model to display employee badges in Many2one dropdown format
    This allows "Search More..." and type-to-filter functionality
    """
    _name = 'employee.badge'
    _description = 'Employee Badge ID'
    _order = 'badge_id'
    _auto = False  # This is a database view, not a real table
    _rec_name = 'name'  # Use 'name' field for display

    name = fields.Char('Display Name', readonly=True)
    badge_id = fields.Char('Badge ID', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char('Employee Name', readonly=True)

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """Allow searching by badge_id or employee name"""
        domain = domain or []
        if name:
            # Search in badge_id OR employee_name OR the combined name field
            domain = [
                '|', '|',
                ('badge_id', operator, name),
                ('employee_name', operator, name),
                ('name', operator, name)
            ] + domain
        return self._search(domain, limit=limit, order=order)

    def init(self):
        """Create database view for employee badges"""
        self.env.cr.execute("""
            DROP VIEW IF EXISTS employee_badge CASCADE;
            CREATE OR REPLACE VIEW employee_badge AS (
                SELECT 
                    e.id as id,
                    CONCAT(e.barcode, ' (', e.name, ')') as name,
                    e.barcode as badge_id,
                    e.id as employee_id,
                    e.name as employee_name
                FROM hr_employee e
                WHERE e.barcode IS NOT NULL 
                AND e.barcode != ''
                AND e.active = true
            );
        """)