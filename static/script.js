
const $ = id => document.getElementById(id);

let currentBillId = null;
let lastSavedBill = null;
let allBills = [];
let allCustomers = [];

function money(value) {
    return "₹ " + Number(value).toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function to24(timeStr, ampm) {
    const parts = String(timeStr || "").trim().split(":");
    if (parts.length < 2) return timeStr;
    let h = Number(parts[0]);
    const m = String(parts[1] || "00").trim();
    const mode = String(ampm || "AM").trim().toUpperCase();
    if (!Number.isFinite(h)) return timeStr;
    if (mode === "PM" && h < 12) h += 12;
    if (mode === "AM" && h === 12) h = 0;
    return String(h).padStart(2, "0") + ":" + m.padStart(2, "0");
}

function split12(time24) {
    if (!time24) return { time: "08:00", ampm: "AM" };
    const parts = String(time24).trim().split(":");
    if (parts.length < 2) return { time: time24, ampm: "AM" };
    let h = Number(parts[0]);
    const m = String(parts[1] || "00").trim();
    if (!Number.isFinite(h)) return { time: time24, ampm: "AM" };
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12;
    if (h === 0) h = 12;
    return { time: h + ":" + m.padStart(2, "0"), ampm };
}

function getWorkDescription() {
    const selected = $("workDescription")?.value;
    if (selected === "Other") return $("customWork")?.value?.trim() || "";
    return selected || "";
}

function showStatus(message, error = false) {
    const el = $("statusMessage");
    if (!el) return;
    el.textContent = message;
    el.style.color = error ? "#c62828" : "#14804a";
}

function showToast(message, error = false) {
    let container = document.getElementById("toastContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "toastContainer";
        container.style.cssText = "position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.textContent = message;
    toast.style.cssText = "padding:12px 16px;border-radius:8px;color:#fff;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.2);background:" + (error ? "#c62828" : "#14804a") + ";opacity:0;transition:opacity .2s;";
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity = "1"; });
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 200);
    }, 3000);
}

function formatHours(hours) {
    return Number(hours.toFixed(2)) + " Hours";
}

function getInTime24() {
    const h = Number($("intimeHour")?.value || 0);
    const m = Number($("intimeMinute")?.value || 0);
    const ampm = String($("intimeAmPm")?.value || "AM").toUpperCase();
    let hour = h;
    if (ampm === "PM" && hour < 12) hour += 12;
    if (ampm === "AM" && hour === 12) hour = 0;
    return String(hour).padStart(2, "0") + ":" + String(m).padStart(2, "0");
}

function getOutTime24() {
    const h = Number($("outtimeHour")?.value || 0);
    const m = Number($("outtimeMinute")?.value || 0);
    const ampm = String($("outtimeAmPm")?.value || "PM").toUpperCase();
    let hour = h;
    if (ampm === "PM" && hour < 12) hour += 12;
    if (ampm === "AM" && hour === 12) hour = 0;
    return String(hour).padStart(2, "0") + ":" + String(m).padStart(2, "0");
}

function split24(time24) {
    const parts = String(time24).trim().split(":");
    let h = Number(parts[0] || 0);
    const m = parts[1] || "00";
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12;
    if (h === 0) h = 12;
    return { h: String(h), m: m, ampm: ampm };
}

function getHours() {
    const in24 = getInTime24();
    const out24 = getOutTime24();

    const toMinutes = value => {
        const parts = String(value).trim().split(":").map(Number);
        return parts[0] * 60 + parts[1];
    };

    const start = toMinutes(in24);
    let end = toMinutes(out24);

    if (end < start) end += 1440;

    const breakTime = Number($("breakTime")?.value);
    const breakValue = Number.isFinite(breakTime) ? breakTime : 0;
    if (breakValue < 0) throw new Error("Break time must be non-negative.");

    const hours = (end - start) / 60 - breakValue;
    if (hours <= 0) throw new Error("Working hours must be greater than zero.");
    if (hours > 24) throw new Error("Working hours cannot exceed 24.");
    return Math.round(hours * 100) / 100;
}

function readForm() {
    const customer = $("customerName")?.value?.trim() || "";
    const description = getWorkDescription();
    const rateText = $("rate")?.value?.trim() || "";
    const betaText = $("betaRate")?.value?.trim() || "";
    const rate = Number(rateText);
    const beta = Number(betaText);

    if (!customer || !description) {
        throw new Error("Enter the customer and work description.");
    }

    if (customer.length > 150 || description.length > 250) {
        throw new Error("Customer or work description is too long.");
    }

    if (!rateText || !Number.isFinite(rate) ||
        rate < 0 || rate > 100000000) {
        throw new Error("Enter a valid hourly rate.");
    }

    if (betaText === "" || !Number.isFinite(beta) || beta < 0) {
        throw new Error("Enter a valid beta amount.");
    }

    const hours = getHours();
    const subtotal = Math.round((hours * rate + Number.EPSILON) * 100) / 100;
    const betaAmount = Math.round((hours * beta + Number.EPSILON) * 100) / 100;

    const intime24 = getInTime24();
    const outtime24 = getOutTime24();

    return {
        customer_name: customer,
        work_description: description,
        intime: intime24,
        outtime: outtime24,
        break_time: Number($("breakTime")?.value || 0),
        start_time: intime24,
        end_time: outtime24,
        total_hours: hours,
        rate,
        beta_rate: beta,
        subtotal,
        beta_amount: betaAmount,
        total_amount: Math.round((subtotal + betaAmount) * 100) / 100
    };
}

function indianWords(number) {
    const ones = [
        "Zero", "One", "Two", "Three", "Four", "Five",
        "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
        "Twelve", "Thirteen", "Fourteen", "Fifteen",
        "Sixteen", "Seventeen", "Eighteen", "Nineteen"
    ];
    const tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty",
        "Sixty", "Seventy", "Eighty", "Ninety"
    ];

    function under1000(n) {
        const words = [];
        if (n >= 100) {
            words.push(ones[Math.floor(n / 100)] + " Hundred");
            n %= 100;
        }
        if (n >= 20) {
            words.push(tens[Math.floor(n / 10)]);
            n %= 10;
        }
        if (n > 0) words.push(ones[n]);
        return words.join(" ");
    }

    function numberWords(n) {
        if (n === 0) return "Zero";
        const words = [];

        for (const [divisor, label] of [
            [10000000, "Crore"],
            [100000, "Lakh"],
            [1000, "Thousand"]
        ]) {
            const part = Math.floor(n / divisor);
            if (part) {
                words.push(under1000(part) + " " + label);
                n %= divisor;
            }
        }

        if (n) words.push(under1000(n));
        return words.join(" ");
    }

    const paiseTotal = Math.round(number * 100);
    const rupees = Math.floor(paiseTotal / 100);
    const paise = paiseTotal % 100;
    let result = "Rupees " + numberWords(rupees);

    if (paise) result += " and " + under1000(paise) + " Paise";
    return result + " Only";
}

function renderBill(bill) {
    const setText = (id, value) => {
        if ($(id)) $(id).textContent = value;
    };

    // Show the persisted identity first so it is never lost.
    setText("billingId", bill.bill_id || bill.invoice_no || "Not saved");
    setText("invoiceDate", bill.created_at || "Not saved");

    if ($("totalHours")) $("totalHours").value = formatHours(Number(bill.total_hours) || 0);
    setText("invoiceCustomer", bill.customer_name);
    setText("invoiceDescription", bill.work_description);
    setText("invoiceIntime", bill.intime || bill.start_time || "—");
    setText("invoiceBreak", (bill.break_time ?? bill.breaktime ?? 0) + " hr");
    setText("invoiceOuttime", bill.outtime || bill.end_time || "—");

    setText("tableDescription", bill.work_description);
    setText("tableHours", Number(bill.total_hours).toFixed(2));
    setText("tableRate", Number(bill.rate || 0).toFixed(2));
    setText("tableAmount", Number(bill.subtotal || 0).toFixed(2));

    setText("invoiceSubtotal", money(bill.subtotal || 0));
    setText("invoiceTaxLabel", "Beta");
    setText("invoiceTax", money((bill.beta_amount ?? bill.tax_amount ?? 0) || 0));
    setText("invoiceTotal", money(bill.total_amount || 0));
    setText("amountWords", bill.amount_words || indianWords(bill.total_amount));

    setText("summaryHours", formatHours(bill.total_hours));
    setText("summaryRate", money(bill.rate || 0));
    setText("summarySubtotal", money(bill.subtotal || 0));
    setText("summaryTaxLabel", "Beta");
    setText("summaryTax", money((bill.beta_amount ?? bill.tax_amount ?? 0) || 0));
    setText("summaryTotal", money(bill.total_amount || 0));
}

function calculateBill() {
    try {
        let hours = null;
        try {
            hours = getHours();
            if ($("totalHours")) $("totalHours").value = formatHours(hours);
            if ($("summaryHours")) $("summaryHours").textContent = formatHours(hours);
            if ($("tableHours")) $("tableHours").textContent = Number(hours).toString();
        } catch (e) {
            if ($("totalHours")) $("totalHours").value = "";
        }
        const bill = readForm();
        const today = new Date().toLocaleDateString("en-IN", {
            timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric"
        });
        renderBill({
            ...bill,
            bill_id: currentBillId && lastSavedBill
                ? lastSavedBill.bill_id : "Will be generated on save",
            created_at: currentBillId && lastSavedBill
                ? lastSavedBill.created_at : today
        });
        showStatus("Bill calculated. Save it to create a permanent Bill ID.");
        return true;
    } catch (error) {
        showStatus(error.message, true);
        return false;
    }
}

async function saveBill() {
    if (!calculateBill()) return;

    const button = $("saveButton");
    if (button) button.disabled = true;

    try {
        const response = await fetch("/api/bills", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(readForm())
        });

        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Unable to save bill.");

        currentBillId = result.id;
        lastSavedBill = result;
        renderBill(result);
        showStatus("Bill saved successfully: " + result.bill_id);

        await loadHistory();
        await loadCustomers();
    } catch (error) {
        showStatus(error.message, true);
    } finally {
        if (button) button.disabled = false;
    }
}

async function loadHistory() {
    const body = $("historyBody");
    if (!body) return;

    try {
        const response = await fetch("/api/bills");
        if (!response.ok) throw new Error("Unable to load bill history.");

        allBills = await response.json();
        filterHistory();
    } catch (error) {
        body.replaceChildren();
        const row = body.insertRow();
        row.insertCell().textContent = error.message;
    }
}

function filterHistory() {
    const body = $("historyBody");
    if (!body) return;

    const query = ($("historySearch")?.value || "").toLowerCase();
    const filtered = allBills.filter(bill =>
        [bill?.bill_id, bill?.invoice_no, bill?.customer_name,
         bill?.work_description, bill?.created_at]
            .some(value => String(value || "").toLowerCase().includes(query))
    );

    body.replaceChildren();

    if ($("historyCount")) {
        $("historyCount").textContent = `${filtered.length} bill(s) found`;
    }

    if (!filtered.length) {
        const row = body.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 6;
        cell.textContent = "No matching bills found.";
        return;
    }

    for (const bill of filtered) {
        const row = body.insertRow();

        for (const value of [
            bill.bill_id || bill.invoice_no,
            bill.created_at,
            bill.customer_name,
            bill.work_description,
            money(bill.total_amount)
        ]) {
            row.insertCell().textContent = value;
        }

        const action = row.insertCell();
        const button = document.createElement("button");
        button.textContent = "View";
        button.addEventListener("click", () => loadBill(bill.id));
        action.appendChild(button);
    }
}

async function loadBill(id) {
    try {
        const response = await fetch(`/api/bills/${id}`);
        const bill = await response.json();
        if (!response.ok) throw new Error(bill.error || "Bill not found.");

        if ($("customerName")) {
            if ($("customerName")) $("customerName").value = bill.customer_name;
            const inSplit = split24(bill.intime || bill.start_time || "08:00");
            const outSplit = split24(bill.outtime || bill.end_time || "12:30");
            if ($("intimeHour")) $("intimeHour").value = inSplit.h;
            if ($("intimeMinute")) $("intimeMinute").value = inSplit.m;
            if ($("intimeAmPm")) $("intimeAmPm").value = inSplit.ampm;
            if ($("outtimeHour")) $("outtimeHour").value = outSplit.h;
            if ($("outtimeMinute")) $("outtimeMinute").value = outSplit.m;
            if ($("outtimeAmPm")) $("outtimeAmPm").value = outSplit.ampm;
            if ($("breakTime")) $("breakTime").value = bill.break_time ?? bill.breaktime ?? 0;
            if ($("rate")) $("rate").value = bill.rate;
            if ($("betaRate")) $("betaRate").value = bill.beta_rate ?? 0;

            const workSelect = $("workDescription");
            const options = workSelect ? Array.from(workSelect.options) : [];
            const exists = options.some(option =>
                option.value === bill.work_description &&
                option.value !== "Other"
            );

            if (workSelect) workSelect.value = exists
                ? bill.work_description : "Other";

            if ($("customWork")) {
                if ($("customWork")) { $("customWork").classList.toggle("hidden", exists); $("customWork").value = exists ? "" : bill.work_description; }
            }

            currentBillId = bill.id;
            lastSavedBill = bill;
            renderBill(bill);
            showStatus("Saved bill loaded. Saving again will create another bill.");
            window.history.replaceState({}, "", "/");
            $("new-bill")?.scrollIntoView({ behavior: "smooth" });
        } else {
            window.location.href = `/?bill=${encodeURIComponent(id)}`;
        }
    } catch (error) {
        showToast(error.message, true);
    }
}

function newBill() {
    if (!$("customerName")) return;

    if ($("customerName")) $("customerName").value = "";
    if ($("workDescription")) $("workDescription").selectedIndex = 0;
    if ($("customWork")) { $("customWork").value = ""; $("customWork").classList.add("hidden"); }
    if ($("intimeHour")) $("intimeHour").value = "8";
    if ($("intimeMinute")) $("intimeMinute").value = "00";
    if ($("intimeAmPm")) $("intimeAmPm").value = "AM";
    if ($("outtimeHour")) $("outtimeHour").value = "12";
    if ($("outtimeMinute")) $("outtimeMinute").value = "30";
    if ($("outtimeAmPm")) $("outtimeAmPm").value = "PM";
    if ($("breakTime")) $("breakTime").value = "0";
    if ($("totalHours")) $("totalHours").value = "";
    if ($("rate")) $("rate").value = "1500";
    if ($("betaRate")) $("betaRate").value = "5";

    currentBillId = null;
    lastSavedBill = null;

    ["billingId", "invoiceDate", "invoiceCustomer",
     "invoiceDescription", "invoiceIntime", "invoiceBreak",
     "invoiceOuttime"].forEach(id => {
        if ($(id)) $(id).textContent = "—";
    });

    try { calculateBill(); } catch (e) {}
    showStatus("Form cleared.");
    try { calculateBill(); } catch (e) {}
}

async function loadCustomers() {
    const body = $("customerBody");
    if (!body) return;

    try {
        const response = await fetch("/api/customers");
        if (!response.ok) throw new Error("Unable to load customers.");

        allCustomers = await response.json();
        filterCustomers();
    } catch (error) {
        body.replaceChildren();
        const row = body.insertRow();
        row.insertCell().textContent = error.message;
    }
}

function filterCustomers() {
    const body = $("customerBody");
    if (!body) return;

    const query = ($("customerSearch")?.value || "").toLowerCase();
    const customers = allCustomers.filter(customer =>
        String(customer?.customer_name || "").toLowerCase().includes(query)
    );

    body.replaceChildren();

    if (!customers.length) {
        const row = body.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 4;
        cell.textContent = "No customers found. Save a bill to add a customer.";
        return;
    }

    for (const customer of customers) {
        const row = body.insertRow();
        row.insertCell().textContent = customer.customer_name;
        row.insertCell().textContent = customer.total_bills;
        row.insertCell().textContent = money(customer.total_amount || 0);
        row.insertCell().textContent = customer.last_billing_date || "—";
    }
}

const clearBill = newBill;

function printBill() {
    if (calculateBill()) window.print();
}

function downloadPDF() {
    if (calculateBill()) window.print();
}

// Live IST clock for every page.
function updateClock() {
    const clock = $("datetime");
    if (!clock) return;

    clock.textContent = new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true
    }).format(new Date()) + " IST";
}

if ($("workDescription")) {
    $("workDescription").addEventListener("change", () => {
        const other = $("workDescription").value === "Other";
        if ($("customWork")) {
            $("customWork").classList.toggle("hidden", !other);
            if (other) $("customWork").focus();
        }
        currentBillId = null;
        lastSavedBill = null;
        try { calculateBill(); } catch (e) {}
    });

    ["intimeHour", "intimeMinute", "intimeAmPm", "outtimeHour", "outtimeMinute", "outtimeAmPm", "breakTime", "rate", "betaRate", "customerName"]
        .forEach(id => {
            const el = $(id);
            if (!el) return;
            const handler = () => {
                currentBillId = null;
                lastSavedBill = null;
                try { calculateBill(); } catch (e) {}
            };
            el.addEventListener("input", handler);
            el.addEventListener("change", handler);
        });

    if (new URLSearchParams(window.location.search).has("bill")) {
        loadBill(new URLSearchParams(window.location.search).get("bill"));
    } else {
        calculateBill();
    }
}

updateClock();
setInterval(updateClock, 1000);


async function deleteBill(id) {
    if (!confirm("Delete this bill?")) return;
    try {
        const response = await fetch(`/api/bills/${id}`, { method: "DELETE" });
        if (!response.ok) {
            const result = await response.json();
            throw new Error(result.error || "Unable to delete bill.");
        }
        showStatus("Bill deleted.");
        // Refresh history (HTMX or full reload)
        if (window.htmx) {
            htmx.ajax("GET", "/partials/history", {target: "#historyBody", swap: "innerHTML"});
        } else {
            window.location.reload();
        }
    } catch (error) {
        showStatus(error.message, true);
    }
}
