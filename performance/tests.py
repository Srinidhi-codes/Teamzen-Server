from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model

from organizations.models import Organization
from performance.models import PerformanceCycle, Goal, PerformanceReview
from performance.graphql.queries import PerformanceQuery, _scope_goals

User = get_user_model()


def make_org(name, plan="elite"):
    return Organization.objects.create(
        name=name,
        headquarters_address="1 Test Street",
        plan=plan,
    )


def make_user(email, role, org=None, **kwargs):
    return User.objects.create_user(
        username=email.split("@")[0] + role[:2],
        email=email,
        password="pass12345",
        role=role,
        organization=org,
        **kwargs,
    )


class PerformanceScopingTests(TestCase):
    def setUp(self):
        self.org = make_org("Scope Perf Org")
        self.admin = make_user("scope-admin@test.com", "admin", self.org)
        self.manager = make_user("scope-mgr@test.com", "manager", self.org)
        self.emp = make_user(
            "scope-emp@test.com", "employee", self.org, manager=self.manager
        )
        self.other = make_user("scope-other@test.com", "employee", self.org)
        self.cycle = PerformanceCycle.objects.create(
            organization=self.org,
            name="Q1",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            status="active",
        )
        Goal.objects.create(
            organization=self.org, user=self.emp, title="Emp goal", cycle=self.cycle
        )
        Goal.objects.create(
            organization=self.org, user=self.other, title="Other goal", cycle=self.cycle
        )
        PerformanceReview.objects.create(
            organization=self.org,
            cycle=self.cycle,
            employee=self.emp,
            reviewer=self.manager,
        )
        PerformanceReview.objects.create(
            organization=self.org,
            cycle=self.cycle,
            employee=self.other,
        )

    def test_employee_sees_own_goals_only(self):
        qs = Goal.objects.filter(organization=self.org)
        scoped = _scope_goals(qs, self.emp)
        self.assertEqual(scoped.count(), 1)
        self.assertEqual(scoped.first().user_id, self.emp.id)

    def test_manager_sees_team_goals(self):
        qs = Goal.objects.filter(organization=self.org)
        scoped = _scope_goals(qs, self.manager)
        ids = set(scoped.values_list("user_id", flat=True))
        self.assertIn(self.emp.id, ids)
        self.assertNotIn(self.other.id, ids)

    def test_admin_sees_all_goals(self):
        qs = Goal.objects.filter(organization=self.org)
        scoped = _scope_goals(qs, self.admin)
        self.assertEqual(scoped.count(), 2)

    def test_overview_for_admin(self):
        class R:
            user = self.admin

        class C:
            request = R()

        class Info:
            context = C()

        overview = PerformanceQuery().performance_overview(Info())
        self.assertEqual(overview.active_cycles, 1)
        self.assertEqual(overview.goals_total, 2)
        self.assertGreaterEqual(overview.pending_reviews, 1)
