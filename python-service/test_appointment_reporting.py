from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
import test_account_auth as accounts
import test_service_appointments as bookings
from workspace_reporting import appointments


class AppointmentReportContracts(unittest.TestCase):
    def test_bad_period_rejected_before_database(self):
        with patch('workspace_reporting.scope',return_value=1), patch('workspace_reporting.connect',side_effect=AssertionError('database')):
            with self.assertRaises(HTTPException) as error:
                appointments(datetime.now().date(),None)
            self.assertEqual(error.exception.status_code,422)


@unittest.skipUnless(accounts.DB,'Disposable PostgreSQL required')
class AppointmentReportDatabase(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp=bookings.AppointmentDatabaseTests.setUp
    post=bookings.AppointmentDatabaseTests.post
    login=accounts.AccountDatabaseTests.login
    register=accounts.AccountDatabaseTests.register
    invited=accounts.AccountDatabaseTests.invited

    def create(self,hour):
        day=(datetime.now(timezone.utc)+timedelta(days=3)).replace(hour=hour,minute=0,second=0,microsecond=0)
        return self.post('/api/v1/agenda/appointments',{'operation_id':str(uuid4()),
            'cliente_id':self.person['id'],'servico_id':self.service['id'],'resource_id':self.resource['id'],
            'scheduled_for':day.isoformat(),'notes':'PRIVATE_CLINICAL_NOTE_NOT_RETURNED'})

    def test_persisted_statuses_upcoming_and_history_events_use_distinct_dates(self):
        with patch.dict(os.environ,{'TZ':'America/Recife'}):
            pending=self.create(15)
            completed=self.create(16)
            cancelled=self.create(17)
            path='/api/v1/agenda/appointments/'
            self.assertEqual(self.client.patch(path+completed['id'],json={'expected_revision':1,'status':'done'}).status_code,200)
            self.assertEqual(self.client.patch(path+cancelled['id'],json={'expected_revision':1,'status':'cancelled'}).status_code,200)
            move=datetime.fromisoformat(pending['scheduled_for'])+timedelta(hours=4)
            self.assertEqual(self.client.patch(path+pending['id'],json={'expected_revision':1,'scheduled_for':move.isoformat()}).status_code,200)
            today=datetime.now(timezone(timedelta(hours=-3))).date()
            end=move.date()
            response=self.client.get(f'/api/v1/reporting/appointments?start={today}&end={end}')
            self.assertEqual(response.status_code,200,response.text)
            data=response.json()
            self.assertEqual(data['scheduled'],{'total':3,'pending':1,'done':1,'cancelled':1})
            self.assertEqual(data['upcoming_pending'],1)
            self.assertEqual(data['reschedule_events'],1)
            self.assertEqual(data['services'][0]['total'],3)
            self.assertEqual(data['period']['timezone'],'America/Recife')
            self.assertNotIn('PRIVATE_CLINICAL_NOTE',response.text)
            self.assertNotIn('Cliente fictício',response.text)
            now=self.client.get(f'/api/v1/reporting/appointments?start={today}&end={today}').json()
            self.assertEqual(now['scheduled']['total'],0)
            self.assertEqual(now['reschedule_events'],1)

    def test_timezone_boundary_isolation_roles_and_revocation(self):
        item=self.create(15)
        workspace=self.client.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.agenda_appointments SET scheduled_for='2026-11-05T02:30:00Z',ends_at='2026-11-05T03:00:00Z' WHERE workspace_id=%s AND id=%s",(workspace,item['id']))
        with patch.dict(os.environ,{'TZ':'America/Recife'}):
            self.assertEqual(self.client.get('/api/v1/reporting/appointments?start=2026-11-04&end=2026-11-04').json()['scheduled']['total'],1)
            self.assertEqual(self.client.get('/api/v1/reporting/appointments?start=2026-11-05&end=2026-11-05').json()['scheduled']['total'],0)
        other=self.register('report-other@example.test')
        self.assertEqual(other.get('/api/v1/reporting/appointments').json()['scheduled']['total'],0)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s",(self.admin_id,))
        self.assertEqual(self.client.get('/api/v1/reporting/appointments').status_code,200)
        self.assertEqual(self.client.get('/api/v1/clientes').status_code,403)
        self.assertEqual(self.client.post('/api/v1/auth/logout',json={}).status_code,204)
        self.assertEqual(self.client.get('/api/v1/reporting/appointments').status_code,401)


if __name__=='__main__': unittest.main()
