from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages


def register(request):
    """Registro de nuevos usuarios"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, '¡Cuenta creada exitosamente!')
            return redirect('trading_bot:dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'cuentas/register.html', {'form': form})


@login_required
def profile(request):
    """Perfil del usuario"""
    return render(request, 'cuentas/profile.html')
