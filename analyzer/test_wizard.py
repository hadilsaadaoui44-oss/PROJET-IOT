from django.test import TestCase
from django.urls import reverse

from .models import CustomUser, Project


class EnergyWizardTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='wizard@example.com',
            password='test-password-123',
        )
        self.client.force_login(self.user)

    def test_workflow_intro_is_available(self):
        response = self.client.get(reverse('workflow_intro'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Comment préparer votre analyse')

    def test_first_step_creates_a_draft(self):
        response = self.client.post(reverse('wizard_project'), {
            'name': 'Station test',
            'description': 'Projet IoT de validation',
            'location_city': 'Tunis',
            'location_country': 'Tunisie',
            'latitude': '36.8065',
            'longitude': '10.1815',
            'installation_type': 'outdoor',
        })
        project = Project.objects.get(name='Station test')
        self.assertEqual(project.status, 'draft')
        self.assertEqual(project.user, self.user)
        self.assertRedirects(
            response,
            reverse('wizard_mcu', args=[project.id]),
        )

    def test_other_user_cannot_open_draft(self):
        project = Project.objects.create(
            user=self.user,
            name='Privé',
            location_city='Sousse',
            location_country='Tunisie',
            installation_type='outdoor',
        )
        other = CustomUser.objects.create_user(
            email='other@example.com',
            password='test-password-123',
        )
        self.client.force_login(other)
        response = self.client.get(
            reverse('wizard_mcu', args=[project.id])
        )
        self.assertEqual(response.status_code, 404)
