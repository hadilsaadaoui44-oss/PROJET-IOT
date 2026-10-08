(() => {
    const dataElement = document.getElementById("dashboard-chart-data");
    if (!dataElement || typeof Chart === "undefined") {
        return;
    }

    let chartData = {};
    try {
        chartData = JSON.parse(dataElement.textContent || "{}");
    } catch (error) {
        console.error("Données des graphiques invalides :", error);
        return;
    }

    const commonGrid = {
        color: "rgba(100, 116, 139, 0.14)"
    };

    const commonTicks = {
        color: "#64748b",
        font: { size: 11 }
    };

    const formatNumber = (value, maximumFractionDigits = 3) => {
        const number = Number(value);
        if (!Number.isFinite(number)) return "—";

        return new Intl.NumberFormat("fr-FR", {
            maximumFractionDigits
        }).format(number);
    };

    /*
     * Les instants identiques ne sont volontairement pas supprimés :
     * ils représentent les changements immédiats entre deux modes.
     * L'axe X linéaire évite leur affichage comme étiquettes dupliquées.
     */
    const buildTimelinePoints = (labels, values) => {
        if (!Array.isArray(labels) || !Array.isArray(values)) return [];

        return labels
            .map((time, index) => ({
                x: Number(time),
                y: Number(values[index])
            }))
            .filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
    };

    /*
     * Détermine automatiquement la fin de la phase active.
     * Le minimum du cycle est considéré comme le courant de veille.
     */
    const getActiveZoomEnd = (labels, values) => {
        const points = buildTimelinePoints(labels, values);

        if (points.length < 2) return null;

        const currents = points.map(point => point.y);
        const minimum = Math.min(...currents);
        const maximum = Math.max(...currents);
        const totalDuration = Math.max(...points.map(point => point.x));

        if (
            !Number.isFinite(totalDuration) ||
            totalDuration <= 0 ||
            maximum <= minimum
        ) {
            return null;
        }

        const tolerance = Math.max(
            (maximum - minimum) * 0.000001,
            0.000001
        );

        const activePoints = points.filter(
            point => point.y > minimum + tolerance
        );

        if (!activePoints.length) return null;

        const activeEnd = Math.max(
            ...activePoints.map(point => point.x)
        );

        if (activeEnd <= 0 || activeEnd >= totalDuration) {
            return null;
        }

        // Petite marge à droite pour rendre la transition visible.
        return Math.min(
            totalDuration,
            Math.max(activeEnd * 1.05, activeEnd + 1)
        );
    };
    const makeTimelineChart = (
        canvasId,
        labels,
        values,
        label,
        unit,
        fill = true,
        stepped = false,
        xMax = null
    ) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const points = buildTimelinePoints(labels, values);

        new Chart(canvas, {
            type: "line",
            data: {
                datasets: [{
                    label,
                    data: points,
                    parsing: false,
                    borderWidth: 2.5,
                    tension: 0,
                    stepped,
                    fill,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderColor: "#2563eb",
                    backgroundColor: fill
                        ? "rgba(37, 99, 235, 0.10)"
                        : "transparent"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: "nearest",
                    axis: "x",
                    intersect: false
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => {
                                if (!items.length) return "";
                                return `Temps : ${formatNumber(items[0].parsed.x, 0)} ms`;
                            },
                            label: (context) => (
                                `${context.dataset.label} : ` +
                                `${formatNumber(context.parsed.y)} ${unit}`
                            )
                        }
                    }
                },
                scales: {
                    x: {
                        type: "linear",
                        min: 0,
                        max: (
                            xMax !== null &&
                            xMax !== undefined &&
                            Number.isFinite(Number(xMax)) &&
                            Number(xMax) > 0
                        )
                            ? Number(xMax)
                            : undefined,
                        grid: commonGrid,
                        ticks: {
                            ...commonTicks,
                            autoSkip: true,
                            maxTicksLimit: 7,
                            callback: value => formatNumber(value, 0)
                        },
                        title: {
                            display: true,
                            text: "Temps (ms)",
                            color: "#64748b"
                        }
                    },
                    y: {
                        grid: commonGrid,
                        ticks: commonTicks,
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: unit,
                            color: "#64748b"
                        }
                    }
                }
            }
        });
    };

    const timeline = chartData.timeline || {};

    const timelineLabels = timeline.labels || [];
    const timelineCurrent = timeline.current || [];
    const timelinePower = timeline.power || [];
    const timelineEnergy = timeline.energy || [];

    /*
     * Vue complète : elle conserve fidèlement toute la durée du cycle.
     * Courant et puissance utilisent un tracé en escalier.
     */
    makeTimelineChart(
        "currentChart",
        timelineLabels,
        timelineCurrent,
        "Courant",
        "mA",
        true,
        true
    );

    /*
     * Zoom automatique : il rend visibles les événements très courts,
     * par exemple le pic de 75 mA pendant 200 ms.
     */
    const activeZoomEnd = getActiveZoomEnd(
        timelineLabels,
        timelineCurrent
    );

    makeTimelineChart(
        "activeCurrentChart",
        timelineLabels,
        timelineCurrent,
        "Courant actif",
        "mA",
        true,
        true,
        activeZoomEnd
    );

    makeTimelineChart(
        "powerChart",
        timelineLabels,
        timelinePower,
        "Puissance",
        "mW",
        true,
        true
    );

    /*
     * L’énergie cumulée reste continue :
     * elle ne doit pas être affichée comme un signal en escalier.
     */
    makeTimelineChart(
        "energyChart",
        timelineLabels,
        timelineEnergy,
        "Énergie cumulée",
        "mWh",
        false,
        false
    );
    const lifecycle = chartData.lifecycle || {};
    const batteryCanvas = document.getElementById("lifecycleBatteryChart");

    if (batteryCanvas) {
        new Chart(batteryCanvas, {
            type: "line",
            data: {
                labels: lifecycle.years || [],
                datasets: [
                    {
                        label: "État de santé (%)",
                        data: lifecycle.battery_health || [],
                        borderColor: "#2563eb",
                        backgroundColor: "rgba(37,99,235,.10)",
                        borderWidth: 2.5,
                        tension: 0.25,
                        pointRadius: 2,
                        yAxisID: "y"
                    },
                    {
                        label: "Autonomie (jours)",
                        data: lifecycle.autonomy || [],
                        borderColor: "#16a34a",
                        backgroundColor: "rgba(22,163,74,.08)",
                        borderWidth: 2.5,
                        tension: 0.25,
                        pointRadius: 2,
                        yAxisID: "y1"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: "#475569", usePointStyle: true }
                    }
                },
                scales: {
                    x: {
                        grid: commonGrid,
                        ticks: commonTicks,
                        title: {
                            display: true,
                            text: "Année",
                            color: "#64748b"
                        }
                    },
                    y: {
                        beginAtZero: false,
                        position: "left",
                        grid: commonGrid,
                        ticks: commonTicks
                    },
                    y1: {
                        beginAtZero: true,
                        position: "right",
                        grid: { drawOnChartArea: false },
                        ticks: commonTicks
                    }
                }
            }
        });
    }

    const solarCanvas = document.getElementById("lifecycleSolarChart");
    if (solarCanvas) {
        new Chart(solarCanvas, {
            type: "line",
            data: {
                labels: lifecycle.years || [],
                datasets: [{
                    label: "Puissance panneau (W)",
                    data: lifecycle.panel_power || [],
                    borderColor: "#f59e0b",
                    backgroundColor: "rgba(245,158,11,.12)",
                    borderWidth: 2.5,
                    tension: 0.25,
                    fill: true,
                    pointRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: "#475569", usePointStyle: true }
                    }
                },
                scales: {
                    x: {
                        grid: commonGrid,
                        ticks: commonTicks,
                        title: {
                            display: true,
                            text: "Année",
                            color: "#64748b"
                        }
                    },
                    y: {
                        beginAtZero: false,
                        grid: commonGrid,
                        ticks: commonTicks
                    }
                }
            }
        });
    }

    const scoreCanvas = document.getElementById("scoreRadarChart");
    const score = chartData.score || {};

    const scoreTranslations = {
        Energy: "Énergie",
        Battery: "Batterie",
        Solar: "Solaire",
        Power: "Électronique",
        Reliability: "Fiabilité"
    };

    if (scoreCanvas) {
        const scoreLabels = (score.labels || []).map(
            item => scoreTranslations[item] || item
        );

        new Chart(scoreCanvas, {
            type: "radar",
            data: {
                labels: scoreLabels,
                datasets: [{
                    label: "Score",
                    data: score.values || [],
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37,99,235,.16)",
                    pointBackgroundColor: "#2563eb",
                    pointBorderColor: "#fff",
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        min: 0,
                        max: 100,
                        ticks: {
                            stepSize: 20,
                            color: "#94a3b8",
                            backdropColor: "transparent"
                        },
                        grid: { color: "rgba(100,116,139,.18)" },
                        angleLines: { color: "rgba(100,116,139,.18)" },
                        pointLabels: {
                            color: "#475569",
                            font: { size: 12, weight: "600" }
                        }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    const navLinks = document.querySelectorAll(".dashboard-nav-link");
    const sections = Array.from(navLinks)
        .map(link => document.querySelector(link.getAttribute("href")))
        .filter(Boolean);

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;

            navLinks.forEach(link => link.classList.remove("active"));
            const active = document.querySelector(
                `.dashboard-nav-link[href="#${entry.target.id}"]`
            );
            if (active) active.classList.add("active");
        });
    }, { rootMargin: "-20% 0px -70% 0px" });

    sections.forEach(section => observer.observe(section));
})();