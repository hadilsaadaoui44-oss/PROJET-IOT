from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Project, Component, Firmware, CustomUser


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'location_city', 'location_country', 'latitude', 'longitude']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Station Meteo'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'location_city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Tunis'}),
            'location_country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Tunisie'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
        }


class ComponentForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ['name', 'category', 'voltage', 'datasheet']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: ESP32'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'voltage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'datasheet': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['datasheet'].required = False


ComponentFormSet = forms.inlineformset_factory(
    Project, Component, form=ComponentForm, extra=1, max_num=None, can_delete=True
)


class FirmwareForm(forms.ModelForm):
    class Meta:
        model = Firmware
        fields = ['input_type', 'source_code', 'code_file', 'flowchart']
        widgets = {
            'input_type': forms.Select(attrs={'class': 'form-select', 'id': 'inputType'}),
            'source_code': forms.Textarea(attrs={'class': 'form-control', 'rows': 15, 'placeholder': '// Code Arduino/C/Python'}),
            'code_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.ino,.cpp,.c,.py'}),
            'flowchart': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.png,.jpg,.jpeg'}),
        }


# ========================
# FORMULAIRE INSCRIPTION EMAIL
# ========================
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'exemple@email.com'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True


# ========================
# FORMULAIRE CONNEXION EMAIL
# ========================
class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget = forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'exemple@email.com',
            'autofocus': True,
        })
        self.fields['username'].label = 'Adresse Email'
        self.fields['password'].widget.attrs.update({'class': 'form-control'})