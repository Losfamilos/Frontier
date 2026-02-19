(function () {
  // Bubble chart on dashboard
  const bubbleCanvas = document.getElementById("bubbleChart");
  if (bubbleCanvas && window.BUBBLE_DATA) {
    const data = window.BUBBLE_DATA.map((d, idx) => ({
      x: idx + 1,
      y: d.score,
      r: Math.max(8, Math.min(30, d.score / 3)),
      theme: d.theme,
      arrow: d.arrow,
      confidence: d.confidence
    }));

    const chart = new Chart(bubbleCanvas, {
      type: "bubble",
      data: {
        datasets: [{
          label: "Top themes",
          data
        }]
      },
      options: {
        parsing: false,
        scales: {
          x: { display: false },
          y: { beginAtZero: true, max: 100 }
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const d = ctx.raw;
                return `${d.theme} | score ${d.y} | ${d.arrow} | ${d.confidence}`;
              }
            }
          }
        },
        onClick: (evt, elements) => {
          if (!elements.length) return;
          const el = elements[0];
          const d = chart.data.datasets[0].data[el.index];
          window.location.href = `/theme/${encodeURIComponent(d.theme)}`;
        }
      }
    });
  }

  // History chart
  const histCanvas = document.getElementById("historyChart");
  if (histCanvas && window.HISTORY_SERIES && window.HISTORY_QUARTERS) {
    const labels = window.HISTORY_QUARTERS;
    const series = window.HISTORY_SERIES;
    const datasets = Object.keys(series).map((k) => ({
      label: k,
      data: series[k]
    }));

    new Chart(histCanvas, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true, max: 100 } }
      }
    });
  }
})();
