# Permission Groups

Permissions control what each user can see and do. Assign the appropriate group based on responsibilities.

## Available Permission Groups

### **Admin**
- Full system access  
- Can manage all data, users, imports, and Django Admin  
- Intended for technical staff or leadership  

### **Manager**
- Nearly full access to the system  
- Can manage users, imports, inventory, and recipes  
- Limited access to developer-only Django Admin actions  

### **Barista**
- View-only access for most areas  
- Can manage recipes, ingredients, and inventory  
- Cannot access: Reports, Manage Users, or Admin  

### **Inventory**
- Focused on stock management  
- Can adjust inventory and costs  
- Cannot access advanced reporting, user management, or Admin  

### **Pending**
- Automatically assigned to newly created accounts  
- Must be elevated by a Manager before gaining access  
- Cannot perform any editing actions  

---

## How to Assign Permissions
1. Go to **Manage Users**.  
2. Select the user you want to update.  
3. Choose the correct permission group from the dropdown.  
4. Save changes.

**TIP:** Keep at least one Admin and two Managers assigned at all times.
