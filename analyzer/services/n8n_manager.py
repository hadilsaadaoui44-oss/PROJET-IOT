"""
Gestionnaire automatique de n8n.
Démarre n8n en arrière-plan quand Django démarre.
"""
import subprocess
import time
import requests
import atexit
import os
import signal

_n8n_process = None


def is_n8n_running():
    """Vérifie si n8n est déjà lancé."""
    try:
        response = requests.get('http://localhost:5678/healthz', timeout=3)
        return response.status_code == 200
    except Exception:
        return False


def start_n8n():
    """Démarre n8n en arrière-plan si pas déjà lancé."""
    global _n8n_process

    if is_n8n_running():
        print("✅ n8n est déjà lancé sur localhost:5678")
        return True

    print("🚀 Démarrage de n8n en arrière-plan...")

    try:
        # Démarrer n8n en arrière-plan
        _n8n_process = subprocess.Popen(
            ['npx', 'n8n', 'start'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

        # Attendre que n8n soit prêt (max 30 secondes)
        for i in range(30):
            time.sleep(1)
            if is_n8n_running():
                print(f"✅ n8n démarré avec succès (en {i+1}s)")
                # Arrêter n8n quand Django s'arrête
                atexit.register(stop_n8n)
                return True

        print("⚠️ n8n n'a pas démarré dans les 30 secondes")
        print("   Le calcul local sera utilisé comme fallback.")
        return False

    except FileNotFoundError:
        print("⚠️ n8n n'est pas installé (npx non trouvé)")
        print("   Le calcul local sera utilisé comme fallback.")
        return False
    except Exception as e:
        print(f"⚠️ Erreur démarrage n8n : {e}")
        print("   Le calcul local sera utilisé comme fallback.")
        return False


def stop_n8n():
    """Arrête n8n quand Django s'arrête."""
    global _n8n_process
    if _n8n_process:
        try:
            print("🛑 Arrêt de n8n...")
            if os.name == 'nt':
                _n8n_process.terminate()
            else:
                os.kill(_n8n_process.pid, signal.SIGTERM)
            _n8n_process.wait(timeout=5)
            print("✅ n8n arrêté")
        except Exception:
            try:
                _n8n_process.kill()
            except Exception:
                pass
        _n8n_process = None