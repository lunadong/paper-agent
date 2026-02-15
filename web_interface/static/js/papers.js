// Paper Browser JavaScript
// Handles fetching, rendering, and pagination of papers

// Current state
let currentPage = 1;
let currentSearch = '';
let currentSort = 'recomm_date';
let currentOrder = 'DESC';
let currentDateFrom = '';
let currentDateTo = '';
let currentTopics = [];  // Array of selected topics
let currentSearchMode = 'semantic';  // Always use semantic search
let monthlyChart = null;  // Chart.js instance

// Fetch papers from API
async function fetchPapers(page = 1, search = '') {
    const container = document.getElementById('papersContainer');
    container.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const params = new URLSearchParams({
            page,
            q: search,
            sort: currentSort,
            order: currentOrder,
            mode: currentSearchMode
        });

        if (currentDateFrom) {
            params.set('date_from', currentDateFrom);
        }
        if (currentDateTo) {
            params.set('date_to', currentDateTo);
        }
        if (currentTopics.length > 0) {
            params.set('topics', currentTopics.join(','));
        }

        const response = await fetch(`/api/papers?${params}`);
        const data = await response.json();

        currentPage = data.page;
        currentSearch = data.search;

        renderStats(data);
        renderPapers(data.papers, data.search_mode);
        renderPagination(data);

        // Update URL without reload
        const url = new URL(window.location);
        url.searchParams.set('page', page);
        if (search) {
            url.searchParams.set('q', search);
        } else {
            url.searchParams.delete('q');
        }
        if (currentDateFrom) {
            url.searchParams.set('from', currentDateFrom);
        } else {
            url.searchParams.delete('from');
        }
        if (currentDateTo) {
            url.searchParams.set('to', currentDateTo);
        } else {
            url.searchParams.delete('to');
        }
        if (currentTopics.length > 0) {
            url.searchParams.set('topics', currentTopics.join(','));
        } else {
            url.searchParams.delete('topics');
        }
        if (currentSearchMode !== 'semantic') {
            url.searchParams.set('mode', currentSearchMode);
        } else {
            url.searchParams.delete('mode');
        }
        window.history.pushState({}, '', url);

    } catch (error) {
        container.innerHTML = '<div class="no-results">Error loading papers.</div>';
        console.error('Error fetching papers:', error);
    }
}

// Render stats
function renderStats(data) {
    const stats = document.getElementById('stats');
    if (data.total_papers > 0) {
        let text = `Showing ${data.start + 1}-${data.end} of ${data.total_papers} papers`;
        if (data.search) {
            text += ` matching "${data.search}"`;
        }
        stats.textContent = text;
    } else {
        stats.textContent = '';
    }

    // Decide which chart to show
    // Line chart: when search or topic filter is active
    // Bar chart: default view (no search) or just date filter
    const showLineChart = currentSearch || currentTopics.length > 0;

    if (showLineChart) {
        // Show line chart for search/topic filter results
        renderMonthlyChart(data.monthly_stats);
    } else {
        // Show bar chart for topic distribution (default view or date filter only)
        renderTopicBarChart(data.topic_stats);
    }
}

// Render monthly stats line chart
function renderMonthlyChart(monthlyStats) {
    const chartContainer = document.getElementById('chartContainer');
    const canvas = document.getElementById('monthlyChart');

    // Check if any filter is active
    const hasActiveFilter = currentSearch || currentTopics.length > 0 || currentDateFrom || currentDateTo;

    // Count months with data > 0
    const monthsWithData = monthlyStats ? monthlyStats.filter(d => d.count > 0).length : 0;

    // Show chart only if there's data AND filters are applied AND at least 2 months with data
    if (!monthlyStats || monthlyStats.length === 0 || !hasActiveFilter || monthsWithData < 2) {
        chartContainer.style.display = 'none';
        if (monthlyChart) {
            monthlyChart.destroy();
            monthlyChart = null;
        }
        return;
    }

    chartContainer.style.display = 'block';

    // Destroy existing chart if any
    if (monthlyChart) {
        monthlyChart.destroy();
    }

    // Prepare data
    const labels = monthlyStats.map(d => {
        // Convert "2024-01" to "Jan '24"
        const [year, month] = d.month.split('-');
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${months[parseInt(month) - 1]} '${year.slice(2)}`;
    });
    const counts = monthlyStats.map(d => d.count);

    // Create chart
    monthlyChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Papers',
                data: counts,
                borderColor: '#4a90d9',
                backgroundColor: 'rgba(74, 144, 217, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            size: 10
                        },
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#eee'
                    },
                    ticks: {
                        font: {
                            size: 10
                        },
                        stepSize: 1
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
}

// Topic name mapping for tooltips
const topicFullNames = {
    'Pretraining': 'Pretraining',
    'RL': 'Reinforcement Learning',
    'Reasoning': 'Reasoning',
    'Factuality': 'Factuality',
    'RAG': 'Retrieval-Augmented Generation',
    'Agent': 'Agent',
    'P13N': 'Personalization',
    'Memory': 'Memory',
    'KG': 'Knowledge Graph',
    'QA': 'Question Answering',
    'Recommendation': 'Recommendation',
    'MM': 'Multimodal',
    'Speech': 'Speech',
    'Benchmark': 'Benchmark'
};

// Render topic distribution bar chart (for default view with no search/filter)
function renderTopicBarChart(topicStats) {
    const chartContainer = document.getElementById('chartContainer');
    const canvas = document.getElementById('monthlyChart');

    // Show chart only if there's data
    if (!topicStats || topicStats.length === 0) {
        chartContainer.style.display = 'none';
        if (monthlyChart) {
            monthlyChart.destroy();
            monthlyChart = null;
        }
        return;
    }

    chartContainer.style.display = 'block';

    // Destroy existing chart if any
    if (monthlyChart) {
        monthlyChart.destroy();
    }

    // Prepare data (already sorted by count descending from backend)
    const labels = topicStats.map(d => d.topic);
    const counts = topicStats.map(d => d.count);

    // Generate gradient from dark blue to light blue
    const numBars = labels.length;
    const colors = labels.map((_, i) => {
        // Interpolate from dark blue (20, 60, 140) to light blue (135, 190, 230)
        const ratio = numBars > 1 ? i / (numBars - 1) : 0;
        const r = Math.round(20 + ratio * (135 - 20));
        const g = Math.round(60 + ratio * (190 - 60));
        const b = Math.round(140 + ratio * (230 - 140));
        return `rgb(${r}, ${g}, ${b})`;
    });

    // Create chart
    monthlyChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '# Papers',
                data: counts,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',  // Horizontal bar chart
            layout: {
                padding: {
                    right: 40  // Extra space for data labels on longest bars
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            const topic = context[0].label;
                            return topicFullNames[topic] || topic;
                        },
                        label: function() {
                            return '';  // No additional label
                        }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: {
                        color: '#eee'
                    },
                    ticks: {
                        font: {
                            size: 10
                        },
                        stepSize: 1
                    }
                },
                y: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            size: 11
                        }
                    }
                }
            }
        },
        plugins: [{
            // Custom plugin to draw data labels on bars
            id: 'barLabels',
            afterDatasetsDraw: function(chart) {
                const ctx = chart.ctx;
                chart.data.datasets.forEach((dataset, i) => {
                    const meta = chart.getDatasetMeta(i);
                    meta.data.forEach((bar, index) => {
                        const value = dataset.data[index];
                        ctx.fillStyle = '#333';
                        ctx.font = '11px Inter, sans-serif';
                        ctx.textAlign = 'left';
                        ctx.textBaseline = 'middle';
                        // Position the label slightly to the right of the bar
                        ctx.fillText(value, bar.x + 5, bar.y);
                    });
                });
            }
        }]
    });
}

// Format date from YYYY-MM-DD to "Jan 29, 2026" for display
function formatDate(dateStr) {
    if (!dateStr || dateStr === 'N/A') {
        return dateStr || 'N/A';
    }

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // Check if in YYYY-MM-DD format
    const match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (match) {
        const year = match[1];
        const month = parseInt(match[2], 10);
        const day = parseInt(match[3], 10);
        return `${months[month - 1]} ${day}, ${year}`;
    }

    return dateStr;
}

// Render papers
function renderPapers(papers, searchMode = null) {
    const container = document.getElementById('papersContainer');

    if (!papers || papers.length === 0) {
        container.innerHTML = '<div class="no-results">No papers found.</div>';
        return;
    }

    container.innerHTML = papers.map((paper, index) => {
        const abstract = paper.abstract || '';

        const meta = [
            paper.authors,
            paper.venue
        ].filter(Boolean).join(' - ') + (paper.year ? ` (${paper.year})` : '');

        const summaryLink = paper.has_summary
            ? `<a class="summary-link" href="/paper/${paper.id}" target="_blank">📝 Paper summary</a>`
            : '';

        return `
            <div class="paper">
                <div class="paper-header-row">
                    <a class="paper-title" href="${paper.link || '#'}" target="_blank">${paper.title}</a>
                    ${summaryLink}
                </div>
                <div class="paper-meta">${meta}</div>
                <div class="paper-abstract collapsed" id="abstract-${index}">${abstract}</div>
                <div class="paper-footer">
                    <div class="paper-date">Recommended: ${formatDate(paper.recomm_date)}</div>
                    <span class="abstract-toggle" id="toggle-${index}" onclick="toggleAbstract(${index})">more</span>
                </div>
            </div>
        `;
    }).join('');

    // Check which abstracts need the "more" toggle
    papers.forEach((_, index) => {
        const abstractEl = document.getElementById(`abstract-${index}`);
        const toggleEl = document.getElementById(`toggle-${index}`);
        // Hide toggle if content doesn't overflow (less than 5 lines)
        if (abstractEl && toggleEl && abstractEl.scrollHeight <= abstractEl.clientHeight) {
            toggleEl.style.display = 'none';
        }
    });
}

// Toggle abstract expansion
function toggleAbstract(index) {
    const abstractEl = document.getElementById(`abstract-${index}`);
    const toggleEl = document.getElementById(`toggle-${index}`);

    if (abstractEl.classList.contains('collapsed')) {
        abstractEl.classList.remove('collapsed');
        toggleEl.textContent = 'less';
    } else {
        abstractEl.classList.add('collapsed');
        toggleEl.textContent = 'more';
    }
}

// Render pagination
function renderPagination(data) {
    const pagination = document.getElementById('pagination');

    if (data.total_pages <= 1) {
        pagination.innerHTML = '';
        return;
    }

    let html = '';

    // Previous button
    html += `<button onclick="goToPage(${data.page - 1})" ${data.page <= 1 ? 'disabled' : ''}>← Previous</button>`;

    // Page numbers
    for (let p = 1; p <= data.total_pages; p++) {
        if (p === 1 || p === data.total_pages || Math.abs(p - data.page) <= 2) {
            if (p === data.page) {
                html += `<button class="current" disabled>${p}</button>`;
            } else {
                html += `<button onclick="goToPage(${p})">${p}</button>`;
            }
        } else if (Math.abs(p - data.page) === 3) {
            html += '<span style="margin: 0 5px;">...</span>';
        }
    }

    // Next button
    html += `<button onclick="goToPage(${data.page + 1})" ${data.page >= data.total_pages ? 'disabled' : ''}>Next →</button>`;

    pagination.innerHTML = html;
}

// Go to specific page
function goToPage(page) {
    fetchPapers(page, currentSearch);
}

// Search papers
function searchPapers() {
    const searchInput = document.getElementById('searchInput');
    currentSearch = searchInput.value.trim();
    fetchPapers(1, currentSearch);
}

// Handle Enter key in search box
function handleKeyPress(event) {
    if (event.key === 'Enter') {
        searchPapers();
    }
}

// Apply date filters
function applyFilters() {
    currentDateFrom = document.getElementById('dateFrom').value;
    currentDateTo = document.getElementById('dateTo').value;
    fetchPapers(1, currentSearch);
}

// Clear date filters
function clearFilters() {
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    currentDateFrom = '';
    currentDateTo = '';
    fetchPapers(1, currentSearch);
}

// Clear search
function clearSearch() {
    document.getElementById('searchInput').value = '';
    currentSearch = '';
    fetchPapers(1, '');
}

// Toggle search mode (semantic vs keyword)
function toggleSearchMode() {
    const toggle = document.getElementById('semanticToggle');
    currentSearchMode = toggle.checked ? 'semantic' : 'keyword';

    // Re-run search if there's an active search query
    if (currentSearch) {
        fetchPapers(1, currentSearch);
    }
}

// Clear all topic filters
function clearAllTopics() {
    currentTopics = [];
    updateTopicButtons();
    fetchPapers(1, currentSearch);
}

// Toggle topic filter (multi-select)
function toggleTopicFilter(topic) {
    const index = currentTopics.indexOf(topic);
    if (index > -1) {
        // Remove if already selected
        currentTopics.splice(index, 1);
    } else {
        // Add if not selected
        currentTopics.push(topic);
    }

    // Update button states
    updateTopicButtons();

    // Fetch papers with new filters
    fetchPapers(1, currentSearch);
}

// Update topic button active states
function updateTopicButtons() {
    const buttons = document.querySelectorAll('.topic-filters button:not(.clear-all)');
    buttons.forEach(btn => {
        const match = btn.getAttribute('onclick').match(/'([^']+)'/);
        if (match) {
            const btnTopic = match[1];
            if (currentTopics.includes(btnTopic)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }
    });
}

// Handle browser back/forward buttons
window.onpopstate = function() {
    const params = new URLSearchParams(window.location.search);
    const page = parseInt(params.get('page')) || 1;
    const search = params.get('q') || '';
    currentDateFrom = params.get('from') || '';
    currentDateTo = params.get('to') || '';
    currentTopics = params.get('topics') ? params.get('topics').split(',') : [];

    document.getElementById('searchInput').value = search;
    document.getElementById('dateFrom').value = currentDateFrom;
    document.getElementById('dateTo').value = currentDateTo;
    updateTopicButtons();

    fetchPapers(page, search);
};

// Initial load
document.addEventListener('DOMContentLoaded', function() {
    const params = new URLSearchParams(window.location.search);
    const page = parseInt(params.get('page')) || 1;
    const search = params.get('q') || '';

    // Default date range: 2023-01-01 to today
    const today = new Date().toISOString().split('T')[0];
    currentDateFrom = params.get('from') || '2023-01-01';
    currentDateTo = params.get('to') || today;
    currentTopics = params.get('topics') ? params.get('topics').split(',') : [];

    document.getElementById('searchInput').value = search;
    document.getElementById('dateFrom').value = currentDateFrom;
    document.getElementById('dateTo').value = currentDateTo;
    updateTopicButtons();

    fetchPapers(page, search);
});
