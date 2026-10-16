
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

function getWorkDescription() {
    const selected = $("workDescription")?.value;
    if (selected === "Other") return $("customWork").value.trim();
    return selected || "";
}

function showStatus(message, error = false) {
    const el = $("statusMessage");
    if (!el) return;
    el.textContent = message;
    el.style.color = error ? "#c62828" : "#14804a";
}

function formatHours(hours) {
    return Number(hours.toFixed(2)) + " Hours";
}

function getHours() {
    const startText = $("startTime").value;
    const endText = $("endTime").value;

    if (!startText || !endText) {
        throw new Error("Select both start and end times.");
    }

    const toMinutes = value => {
        const parts = value.split(":").map(Number);
        return parts[0] * 60 + parts[1];
    };

    const start = toMinutes(startText);
    let end = toMinutes(endText);

    // Supports work ending after midnight.
    if (end < start) end += 1440;

    const hours = (end - start) / 60;

    if (hours <= 0) {
        throw new Error("Working hours must be greater than zero.");
    }

    return hours;
}

function readForm() {
    const customer = $("customerName").value.trim();
    const description = getWorkDescription();
    const rateText = $("rate").value.trim();
    const taxText = $("taxRate").value.trim();
    const rate = Number(rateText);
    const tax = Number(taxText);

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

    if (!taxText || !Number.isFinite(tax) || tax < 0 || tax > 100) {
        throw new Error("Enter a tax percentage from 0 to 100.");
    }

    const hours = getHours();
    const subtotal = Math.round((hours * rate + Number.EPSILON) * 100) / 100;
    const taxAmount = Math.round((subtotal * tax / 100 + Number.EPSILON) * 100) / 100;

    return {
        customer_name: customer,
        work_description: description,
        start_time: $("startTime").value,
        end_time: $("endTime").value,
        total_hours: hours,
        rate,
        tax_percentage: tax,
        subtotal,
        tax_amount: taxAmount,
        total_amount: Math.round((subtotal + taxAmount) * 100) / 100
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
    if ($("totalHours")) $("totalHours").value = formatHours(bill.total_hours);

    const setText = (id, value) => {
        if ($(id)) $(id).textContent = value;
    };

    setText("invoiceNumber", bill.bill_id || bill.invoice_no || "Not saved");
    setText("invoiceDate", bill.created_at || "Not saved");
    setText("invoiceCustomer", bill.customer_name);
    setText("invoiceDescription", bill.work_description);
    setText("invoiceTime", `${bill.start_time} – ${bill.end_time} IST`);

    setText("tableDescription", bill.work_description);
    setText("tableHours", Number(bill.total_hours).toString());
    setText("tableRate", Number(bill.rate).toFixed(2));
    setText("tableAmount", Number(bill.subtotal).toFixed(2));

    setText("invoiceSubtotal", money(bill.subtotal));
    setText("invoiceTaxLabel", `Tax (${bill.tax_percentage}%)`);
    setText("invoiceTax", money(bill.tax_amount));
    setText("invoiceTotal", money(bill.total_amount));
    setText("amountWords", bill.amount_words || indianWords(bill.total_amount));

    setText("summaryHours", formatHours(bill.total_hours));
    setText("summaryRate", money(bill.rate));
    setText("summarySubtotal", money(bill.subtotal));
    setText("summaryTaxLabel", `Tax (${bill.tax_percentage}%)`);
    setText("summaryTax", money(bill.tax_amount));
    setText("summaryTotal", money(bill.total_amount));
}

function calculateBill() {
    try {
        const bill = readForm();
        renderBill({
            ...bill,
            bill_id: currentBillId && lastSavedBill
                ? lastSavedBill.bill_id : "Not saved",
            created_at: currentBillId && lastSavedBill
                ? lastSavedBill.created_at : "Not saved"
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
        [bill.bill_id, bill.invoice_no, bill.customer_name,
         bill.work_description, bill.created_at]
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
            $("customerName").value = bill.customer_name;
            $("startTime").value = bill.start_time;
            $("endTime").value = bill.end_time;
            $("rate").value = bill.rate;
            $("taxRate").value = bill.tax_percentage;

            const options = Array.from($("workDescription").options);
            const exists = options.some(option =>
                option.value === bill.work_description &&
                option.value !== "Other"
            );

            $("workDescription").value = exists
                ? bill.work_description : "Other";

            if ($("customWork")) {
                $("customWork").classList.toggle("hidden", exists);
                $("customWork").value = exists ? "" : bill.work_description;
            }

            currentBillId = bill.id;
            lastSavedBill = bill;
            renderBill(bill);
            showStatus("Saved bill loaded. Saving again will create another bill.");
            window.history.replaceState({}, "", "/");
            $("new-bill").scrollIntoView({ behavior: "smooth" });
        } else {
            window.location.href = `/?bill=${encodeURIComponent(id)}`;
        }
    } catch (error) {
        alert(error.message);
    }
}

function newBill() {
    if (!$("customerName")) return;

    $("customerName").value = "";
    $("workDescription").selectedIndex = 0;
    $("customWork").value = "";
    $("customWork").classList.add("hidden");
    $("startTime").value = "08:00";
    $("endTime").value = "12:30";
    $("totalHours").value = "";
    $("rate").value = "1500";
    $("taxRate").value = "0";

    currentBillId = null;
    lastSavedBill = null;

    ["invoiceNumber", "invoiceDate", "invoiceCustomer",
     "invoiceDescription", "invoiceTime"].forEach(id => {
        if ($(id)) $(id).textContent = "—";
    });

    renderBill({
        total_hours: 0, rate: 0, subtotal: 0,
        tax_percentage: 0, tax_amount: 0, total_amount: 0,
        customer_name: "—", work_description: "—",
        start_time: "—", end_time: "—"
    });

    showStatus("Form cleared.");
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
        customer.customer_name.toLowerCase().includes(query)
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
        row.insertCell().textContent = customer.bill_count;
        row.insertCell().textContent = money(customer.total_spent || 0);
        row.insertCell().textContent = customer.last_bill || "—";
    }
}

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
        $("customWork").classList.toggle("hidden", !other);
        if (other) $("customWork").focus();
        currentBillId = null;
        lastSavedBill = null;
    });

    ["startTime", "endTime", "rate", "taxRate", "customerName"]
        .forEach(id => {
            $(id).addEventListener("input", () => {
                currentBillId = null;
                lastSavedBill = null;
            });
        });

    if (new URLSearchParams(window.location.search).has("bill")) {
        loadBill(new URLSearchParams(window.location.search).get("bill"));
    } else {
        calculateBill();
    }
}

updateClock();
setInterval(updateClock, 1000);
