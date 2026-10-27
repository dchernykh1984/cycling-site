# Keep form submissions responsive while two thumbnail requests wait on external storage.
# Threads share the application's memory; extra workers would exceed the small hosting budget.
threads = 4
