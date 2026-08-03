from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from graphql import GraphQLError

from organizations.models import Organization
from organizations.plan_entitlements import require_feature
from reports.auth import require_reports_access, resolve_report_org
from performance.auth import require_performance_access, resolve_perf_org
from performance.models import PerformanceCycle, Goal, PerformanceReview

User = get_user_model()


def make_org(name, plan="free"):
    return Organization.objects.create(
        name=name,
        headquarters_address="1 Test Street",
        plan=plan,
    )


def make_user(email, role, org=None, **kwargs):
    return User.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="pass12345",
        role=role,
        organization=org,
        **kwargs,
    )


class ReportsAuthTests(TestCase):
    def setUp(self):
        self.org_free = make_org("Free Co Reports", "free")
        self.org_elite = make_org("Elite Co Reports", "elite")
        self.admin_free = make_user("admin-free@test.com", "admin", self.org_free)
        self.admin_elite = make_user("admin-elite@test.com", "admin", self.org_elite)
        self.hr_elite = make_user("hr-elite@test.com", "hr", self.org_elite)
        self.employee = make_user("emp@test.com", "employee", self.org_elite)
        self.superadmin = make_user("super@test.com", "superadmin", is_superuser=True)

    def test_require_feature_blocks_free(self):
        with self.assertRaises(GraphQLError):
            require_feature(self.org_free, "advanced_analytics")

    def test_require_feature_allows_elite(self):
        require_feature(self.org_elite, "advanced_analytics")

    def test_reports_access_roles(self):
        require_reports_access(self.admin_elite)
        require_reports_access(self.hr_elite)
        require_reports_access(self.superadmin)
        with self.assertRaises(Exception):
            require_reports_access(self.employee)

    def test_resolve_report_org_enforces_elite(self):
        with self.assertRaises(GraphQLError):
            resolve_report_org(self.admin_free)
        org = resolve_report_org(self.admin_elite)
        self.assertEqual(org.id, self.org_elite.id)

    def test_superadmin_bypasses_feature_and_can_pick_org(self):
        org = resolve_report_org(self.superadmin, self.org_free.id)
        self.assertEqual(org.id, self.org_free.id)


class PerformanceAuthAndScopeTests(TestCase):
    def setUp(self):
        self.org = make_org("Perf Org Elite", "elite")
        self.org_free = make_org("Perf Org Free", "free")
        self.admin = make_user("padmin@test.com", "admin", self.org, first_name="Admin")
        self.manager = make_user("pmgr@test.com", "manager", self.org, first_name="Mgr")
        self.emp = make_user(
            "pemp@test.com",
            "employee",
            self.org,
            manager=self.manager,
            first_name="Emp",
            last_name="One",
        )
        self.admin_free = make_user("pfree@test.com", "admin", self.org_free)
        self.cycle = PerformanceCycle.objects.create(
            organization=self.org,
            name="H1 2026",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=60),
            status="active",
            created_by=self.admin,
        )

    def test_performance_feature_gate(self):
        with self.assertRaises(GraphQLError):
            resolve_perf_org(self.admin_free)
        self.assertEqual(resolve_perf_org(self.admin).id, self.org.id)

    def test_employee_can_access_performance(self):
        require_performance_access(self.emp, allow_employee=True)

    def test_employee_blocked_from_admin_only(self):
        with self.assertRaises(Exception):
            require_performance_access(self.emp, allow_employee=False)

    def test_goal_and_review_creation(self):
        goal = Goal.objects.create(
            organization=self.org,
            user=self.emp,
            cycle=self.cycle,
            title="Ship reports",
            progress=40,
            status="in_progress",
        )
        review = PerformanceReview.objects.create(
            organization=self.org,
            cycle=self.cycle,
            employee=self.emp,
            reviewer=self.manager,
            status="pending",
        )
        self.assertEqual(goal.user_id, self.emp.id)
        self.assertEqual(review.cycle_id, self.cycle.id)


class WorkforceReportServiceSmokeTests(TestCase):
    def setUp(self):
        self.org = make_org("WF Org Elite", "elite")
        today = date.today()
        make_user(
            "wf1@test.com",
            "employee",
            self.org,
            is_active=True,
            date_of_joining=today - timedelta(days=120),
            first_name="One",
            last_name="Emp",
        )
        make_user(
            "wf2@test.com",
            "employee",
            self.org,
            is_active=False,
            date_of_joining=today - timedelta(days=400),
            date_of_exit=today - timedelta(days=10),
            first_name="Two",
            last_name="Ex",
        )
        self.admin = make_user("wfadmin@test.com", "admin", self.org)

    def test_workforce_query_returns_kpis(self):
        from reports.graphql.queries import ReportsQuery
        from reports.graphql.types import ReportFilterInput

        class R:
            user = self.admin

        class C:
            request = R()

        class Info:
            context = C()

        result = ReportsQuery().workforce_report(
            Info(),
            ReportFilterInput(
                date_from=date.today() - timedelta(days=180),
                date_to=date.today(),
            ),
        )
        self.assertGreaterEqual(result.active_count, 1)
        self.assertTrue(any(k.label == "Turnover rate" for k in result.kpis))
