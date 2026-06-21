class EnergyCalculator:
    """
    Calcul du bilan energetique.
    Modes DYNAMIQUES : pas de liste fixe.
    PAS de valeurs par defaut.
    """

    def __init__(self, project):
        self.project = project
        self.warnings = []
        

    def analyze(self):
        components = self.project.components.all()

        # ==============================
        # 1. Collecter TOUS les modes
        # ==============================
        all_modes = []
        voltage = 3.3

        for comp in components:
            voltage = comp.voltage or 3.3
            modes = comp.modes.all()

            if not modes.exists():
                self.warnings.append(
                    f'⚠️ {comp.name} : Aucun '
                    f'mode saisi !'
                )
                continue

            for mode in modes:
                if mode.count_per_cycle > 0:
                    all_modes.append({
                        'name': mode.name,
                        'current_ma': (
                            mode.current_ma
                        ),
                        'duration_ms': (
                            mode.duration_ms
                        ),
                        'count': (
                            mode.count_per_cycle
                        ),
                        'component': comp.name,
                    })

        if not all_modes:
            return self._empty_result()

        # ==============================
        # 2. Calcul par mode
        # ==============================
        states = []
        total_energy = 0
        total_cycle = 0
        current_min = float('inf')
        current_max = 0
        mode_min = ''
        mode_max = ''

        for m in all_modes:
            energy = (
                m['current_ma']
                * m['duration_ms']
                * m['count']
            ) / 3600000

            state = {
                'name': m['name'],
                'component': m['component'],
                'current_ma': round(
                    m['current_ma'], 4
                ),
                'duration_ms': m['duration_ms'],
                'count': m['count'],
                'energy_mah': round(energy, 6),
                'power_mw': round(
                    m['current_ma'] * voltage, 2
                ),
            }
            states.append(state)
            total_energy += energy
            total_cycle += (
                m['duration_ms'] * m['count']
            )

            if m['current_ma'] < current_min:
                current_min = m['current_ma']
                mode_min = m['name']
            if m['current_ma'] > current_max:
                current_max = m['current_ma']
                mode_max = m['name']

        # Pourcentages
        for s in states:
            s['energy_percent'] = round(
                (s['energy_mah']
                 / max(total_energy, 0.000001))
                * 100, 1
            )
            s['time_percent'] = round(
                (s['duration_ms'] * s['count']
                 / max(total_cycle, 1))
                * 100, 1
            )

        # ==============================
        # 3. Totaux
        # ==============================
        cycles_day = int(
            86400000 / max(total_cycle, 1)
        )
        daily_mah = round(
            total_energy * cycles_day, 2
        )
        daily_mwh = round(
            daily_mah * voltage, 2
        )
        daily_wh = round(daily_mwh / 1000, 4)

        avg_current = round(
            (total_energy * 3600000
             / max(total_cycle, 1)), 2
        )
        avg_power = round(
            avg_current * voltage, 2
        )

        # ==============================
        # 4. Courbe LIGNE
        # ==============================
        curve = []
        t = 0
        for s in states:
            for _ in range(s['count']):
                curve.append([t, 0])
                curve.append([
                    t + 1, s['current_ma']
                ])
                end = t + int(s['duration_ms'])
                curve.append([
                    end - 1, s['current_ma']
                ])
                curve.append([end, 0])
                t = end

        # ==============================
        # 5. Batterie
        # ==============================
        autonomy = 3
        safety = 1.25
        raw_bat = daily_mah * autonomy
        final_bat = int(raw_bat * safety)

        if final_bat > 2000:
            bat_type = 'LiPo 18650 3.7V'
        elif final_bat > 500:
            bat_type = 'LiPo 3.7V'
        else:
            bat_type = '2x Piles AA 1.5V'

        real_autonomy = round(
            final_bat / max(daily_mah, 0.01), 1
        )

        # ==============================
        # 6. Adaptateur
        # ==============================
        peak_a = round(current_max / 1000, 3)
        adapter_a = round(peak_a * 1.5, 2)

        if voltage <= 3.3:
            adapter_type = 'LDO 3.3V (AMS1117)'
        elif voltage <= 5:
            adapter_type = 'Buck DC-DC 5V-3.3V'
        else:
            adapter_type = 'Buck DC-DC ajustable'

        # ==============================
        # 7. Panneau solaire
        # ==============================
        sun_data = {
            'tunis': {
                'annual': 5.2, 'worst': 3.5
            },
            'sfax': {
                'annual': 5.8, 'worst': 3.8
            },
            'sousse': {
                'annual': 5.4, 'worst': 3.6
            },
            'paris': {
                'annual': 3.5, 'worst': 1.5
            },
        }

        city = (
            self.project.location_city.lower()
        )
        sun = sun_data.get(city, {
            'annual': 4.5, 'worst': 3.0
        })

        panel_eff = 0.85
        charger_eff = 0.90
        margin = 1.25

        panel_raw = daily_wh / max(
            sun['worst'], 0.1
        )
        panel_w = round(
            panel_raw
            / (panel_eff * charger_eff)
            * margin, 2
        )

        if panel_w > 5:
            p_type = 'Monocristallin 12V'
        elif panel_w > 2:
            p_type = 'Monocristallin 6V'
        elif panel_w > 0.5:
            p_type = 'Monocristallin 6V 1W'
        else:
            p_type = 'Mini panneau 5V'

        incl = int(
            self.project.latitude or 35
        )

        # Verdict
        if daily_mah < 1:
            verdict = 'Tres faible consommation'
        elif daily_mah < 100:
            verdict = 'Systeme viable'
        elif daily_mah < 1000:
            verdict = 'Panneau moyen requis'
        else:
            verdict = 'Consommation elevee'

        # ==============================
        # RETOUR 6 BLOCS DU PROF
        # ==============================
        return {
            # BLOC 1 : Resume global
            'summary': {
                'avg_current_ma': avg_current,
                'min_current_ma': round(
                    current_min, 4
                ),
                'min_current_mode': mode_min,
                'max_current_ma': round(
                    current_max, 2
                ),
                'max_current_mode': mode_max,
                'avg_power_mw': avg_power,
                'daily_energy_mah': daily_mah,
                'daily_energy_wh': daily_wh,
                'voltage': voltage,
                'verdict': verdict,
            },

            # BLOC 2 : Detail par mode
            'energy_profile': {
                'states': states,
                'total_energy_mah': round(
                    total_energy, 6
                ),
                'cycle_duration_s': round(
                    total_cycle / 1000, 2
                ),
                'cycles_per_day': cycles_day,
                'daily_energy_mah': daily_mah,
            },

            # BLOC 3 : Courbe
            'consumption_curve': curve,

            # BLOC 4 : Batterie
            'battery_recommendation': {
                'capacity_mah': final_bat,
                'autonomy_days': real_autonomy,
                'type': bat_type,
                'safety_factor': safety,
            },

            # BLOC 5 : Adaptateur
            'adapter_recommendation': {
                'voltage_v': voltage,
                'current_a': adapter_a,
                'peak_current_a': peak_a,
                'type': adapter_type,
            },

            # BLOC 6 : Solaire
            'solar_report': {
                'location': (
                    self.project.location_city
                ),
                'sun_hours': sun['annual'],
                'sun_hours_worst': sun['worst'],
                'panel_w': panel_w,
                'panel_type': p_type,
                'panel_efficiency': panel_eff,
                'charger_efficiency': charger_eff,
                'orientation': 'Sud',
                'inclination': incl,
            },

            # Donnees brutes
            'daily_energy_mah': daily_mah,
            'daily_energy_mwh': daily_mwh,
            'warnings': self.warnings,
        }

    def _empty_result(self):
        self.warnings.append(
            '❌ Aucun mode ! Saisissez les '
            'modes de vos composants.'
        )
        return {
            'summary': {
                'avg_current_ma': 0,
                'min_current_ma': 0,
                'min_current_mode': '-',
                'max_current_ma': 0,
                'max_current_mode': '-',
                'avg_power_mw': 0,
                'daily_energy_mah': 0,
                'daily_energy_wh': 0,
                'voltage': 3.3,
                'verdict': 'Aucune donnee',
            },
            'energy_profile': {
                'states': [],
                'total_energy_mah': 0,
                'cycle_duration_s': 0,
                'cycles_per_day': 0,
                'daily_energy_mah': 0,
            },
            'consumption_curve': [],
            'battery_recommendation': {
                'capacity_mah': 0,
                'autonomy_days': 0,
                'type': '-',
                'safety_factor': 0,
            },
            'adapter_recommendation': {
                'voltage_v': 3.3,
                'current_a': 0,
                'peak_current_a': 0,
                'type': '-',
            },
            'solar_report': {
                'location': '-',
                'sun_hours': 0,
                'panel_w': 0,
                'panel_type': '-',
                'panel_efficiency': 0,
                'charger_efficiency': 0,
            },
            'daily_energy_mah': 0,
            'daily_energy_mwh': 0,
            'warnings': self.warnings,
        }