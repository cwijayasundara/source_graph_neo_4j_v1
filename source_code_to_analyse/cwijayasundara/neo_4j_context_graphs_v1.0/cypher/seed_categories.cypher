// Top-level categories
MERGE (essentials:Category {name: "Essentials"})
MERGE (transport:Category {name: "Transport"})
MERGE (fooddrink:Category {name: "Food & Drink"})
MERGE (subscriptions:Category {name: "Subscriptions"})
MERGE (shopping:Category {name: "Shopping"})
MERGE (children:Category {name: "Children & Education"})
MERGE (telecoms:Category {name: "Telecoms"})
MERGE (health:Category {name: "Health & Wellbeing"})
MERGE (savings:Category {name: "Savings & Investments"})
MERGE (income:Category {name: "Income"})
MERGE (charity:Category {name: "Charity"})

// Essentials subcategories
MERGE (groceries:Category {name: "Groceries"}) MERGE (groceries)-[:SUBCATEGORY_OF]->(essentials)
MERGE (utilities:Category {name: "Utilities"}) MERGE (utilities)-[:SUBCATEGORY_OF]->(essentials)
MERGE (housing:Category {name: "Housing"}) MERGE (housing)-[:SUBCATEGORY_OF]->(essentials)
MERGE (insurance:Category {name: "Insurance"}) MERGE (insurance)-[:SUBCATEGORY_OF]->(essentials)

// Transport subcategories
MERGE (fuel:Category {name: "Fuel"}) MERGE (fuel)-[:SUBCATEGORY_OF]->(transport)
MERGE (publictransport:Category {name: "Public Transport"}) MERGE (publictransport)-[:SUBCATEGORY_OF]->(transport)
MERGE (ridehailing:Category {name: "Ride Hailing"}) MERGE (ridehailing)-[:SUBCATEGORY_OF]->(transport)

// Food & Drink subcategories
MERGE (dining:Category {name: "Dining Out"}) MERGE (dining)-[:SUBCATEGORY_OF]->(fooddrink)
MERGE (takeaways:Category {name: "Takeaways"}) MERGE (takeaways)-[:SUBCATEGORY_OF]->(fooddrink)
MERGE (coffee:Category {name: "Coffee Shops"}) MERGE (coffee)-[:SUBCATEGORY_OF]->(fooddrink)

// Subscriptions subcategories
MERGE (streaming:Category {name: "Streaming"}) MERGE (streaming)-[:SUBCATEGORY_OF]->(subscriptions)
MERGE (software:Category {name: "Software"}) MERGE (software)-[:SUBCATEGORY_OF]->(subscriptions)
MERGE (mealkits:Category {name: "Meal Kits"}) MERGE (mealkits)-[:SUBCATEGORY_OF]->(subscriptions)

// Shopping subcategories
MERGE (clothing:Category {name: "Clothing"}) MERGE (clothing)-[:SUBCATEGORY_OF]->(shopping)
MERGE (homediy:Category {name: "Home & DIY"}) MERGE (homediy)-[:SUBCATEGORY_OF]->(shopping)
MERGE (onlineretail:Category {name: "Online Retail"}) MERGE (onlineretail)-[:SUBCATEGORY_OF]->(shopping)

// Children & Education subcategories
MERGE (school:Category {name: "School"}) MERGE (school)-[:SUBCATEGORY_OF]->(children)
MERGE (tutoring:Category {name: "Tutoring"}) MERGE (tutoring)-[:SUBCATEGORY_OF]->(children)

// Telecoms subcategories
MERGE (mobile:Category {name: "Mobile"}) MERGE (mobile)-[:SUBCATEGORY_OF]->(telecoms)
MERGE (broadband:Category {name: "Broadband"}) MERGE (broadband)-[:SUBCATEGORY_OF]->(telecoms)

// Health & Wellbeing subcategories
MERGE (optical:Category {name: "Optical"}) MERGE (optical)-[:SUBCATEGORY_OF]->(health)
MERGE (pharmacy:Category {name: "Pharmacy"}) MERGE (pharmacy)-[:SUBCATEGORY_OF]->(health)

// Savings & Investments subcategories
MERGE (pension:Category {name: "Pension"}) MERGE (pension)-[:SUBCATEGORY_OF]->(savings)
MERGE (savingstransfers:Category {name: "Savings Transfers"}) MERGE (savingstransfers)-[:SUBCATEGORY_OF]->(savings)
MERGE (roundups:Category {name: "Round-ups"}) MERGE (roundups)-[:SUBCATEGORY_OF]->(savings)

// Income subcategories
MERGE (salary:Category {name: "Salary"}) MERGE (salary)-[:SUBCATEGORY_OF]->(income)

// Charity subcategories
MERGE (donations:Category {name: "Donations"}) MERGE (donations)-[:SUBCATEGORY_OF]->(charity);
