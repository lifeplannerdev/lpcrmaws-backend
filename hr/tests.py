from django.test import TestCase
from django.contrib.auth import get_user_model
from hr.models import Asset, AssetCategory, Branch, Location
from hr.serializers import AssetSerializer, LocationSerializer, StaffSerializer

User = get_user_model()


class StandaloneAssetAndSpaceModelTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username="employee1", email="emp1@test.com", password="password123", company="LP"
        )
        self.user2 = User.objects.create_user(
            username="manager1", email="mgr1@test.com", password="password123", company="LP"
        )
        self.branch = Branch.objects.create(name="HQ Branch", company="LP")
        self.cabin = Location.objects.create(
            name="Cabin 101", company="LP", branch=self.branch, assigned_to=self.user2
        )
        self.cat_mobile, _ = AssetCategory.objects.get_or_create(name="Mobiles")
        self.cat_sim, _ = AssetCategory.objects.get_or_create(name="SIM")
        self.cat_keyboard, _ = AssetCategory.objects.get_or_create(name="Keyboard")
        self.cat_chair, _ = AssetCategory.objects.get_or_create(name="Office Chair")

    def test_asset_saved_independently_without_parent_or_pair(self):
        """Assets must save standalone without requiring parent/pairing."""
        asset = Asset.objects.create(
            name="MacBook Pro 16",
            serial_number="MBP12345",
            company="LP",
            category=self.cat_keyboard,
        )
        self.assertIsNotNone(asset.id)
        self.assertIsNone(asset.primary_sim)
        self.assertIsNone(asset.secondary_sim)
        self.assertIsNone(asset.assigned_to)
        self.assertIsNone(asset.assigned_location)

    def test_asset_linked_to_employee_id(self):
        """Asset can be directly linked to an employee."""
        asset = Asset.objects.create(
            name="iPhone 15",
            company="LP",
            category=self.cat_mobile,
            assigned_to=self.user1,
        )
        asset.refresh_from_db()
        self.assertEqual(asset.assigned_to.id, self.user1.id)

    def test_asset_linked_to_cabin_id(self):
        """Asset can be directly linked to a cabin/space."""
        asset = Asset.objects.create(
            name="Ergonomic Desk Chair",
            company="LP",
            category=self.cat_chair,
            assigned_location=self.cabin,
        )
        asset.refresh_from_db()
        self.assertEqual(asset.assigned_location.id, self.cabin.id)

    def test_general_asset_in_cabin_not_overwritten_by_space_manager(self):
        """General asset in a cabin must NOT inherit space manager as assigned_to."""
        asset = Asset.objects.create(
            name="Conference Table",
            company="LP",
            category=self.cat_chair,
            assigned_location=self.cabin,
            assigned_to=None,
        )
        asset.refresh_from_db()
        # Should remain general asset without assigned_to
        self.assertIsNone(asset.assigned_to)

        # Saving location must NOT force-assign general assets to manager
        self.cabin.save()
        asset.refresh_from_db()
        self.assertIsNone(asset.assigned_to)

    def test_asset_classification(self):
        """Assets and categories resolve into correct classifications."""
        mob = Asset.objects.create(name="Pixel 8", company="LP", category=self.cat_mobile)
        sim = Asset.objects.create(name="Airtel SIM", company="LP", category=self.cat_sim)
        kb = Asset.objects.create(name="Mechanical Keyboard", company="LP", category=self.cat_keyboard)
        chair = Asset.objects.create(name="Mesh Chair", company="LP", category=self.cat_chair)

        self.assertEqual(mob.classification, "Communication Systems")
        self.assertEqual(sim.classification, "Communication Systems")
        self.assertEqual(kb.classification, "System Classification")
        self.assertEqual(chair.classification, "Office Furniture")

        # Serializer includes classification
        serializer = AssetSerializer(mob)
        self.assertEqual(serializer.data["classification"], "Communication Systems")

    def test_cabin_serializer_members_and_general_assets(self):
        """LocationSerializer must split members (with their assets) and general assets."""
        # General asset in cabin (no employee)
        general_asset = Asset.objects.create(
            name="Whiteboard 6x4",
            company="LP",
            assigned_location=self.cabin,
            assigned_to=None,
        )
        # Personal asset assigned to user1 in this cabin
        personal_asset = Asset.objects.create(
            name="Dell Latitude Laptop",
            company="LP",
            assigned_location=self.cabin,
            assigned_to=self.user1,
        )

        serializer = LocationSerializer(self.cabin)
        data = serializer.data

        # Check general assets
        general_asset_ids = [a["id"] for a in data["general_assets"]]
        self.assertIn(general_asset.id, general_asset_ids)
        self.assertNotIn(personal_asset.id, general_asset_ids)

        # Check members
        member_ids = [m["id"] for m in data["members"]]
        self.assertIn(self.user1.id, member_ids)

        user1_member = next(m for m in data["members"] if m["id"] == self.user1.id)
        user1_asset_ids = [a["id"] for a in user1_member["assets"]]
        self.assertIn(personal_asset.id, user1_asset_ids)

    def test_cabin_member_with_direct_assigned_asset(self):
        """Occupant of a cabin who has directly assigned assets (assigned_location=None) must have them in cabin members."""
        self.user1.location = self.cabin.name
        self.user1.save()

        direct_asset = Asset.objects.create(
            name="Direct ThinkPad Laptop",
            company="LP",
            category=self.cat_keyboard,
            assigned_to=self.user1,
            assigned_location=None,
        )

        serializer = LocationSerializer(self.cabin)
        data = serializer.data
        user1_member = next((m for m in data["members"] if m["id"] == self.user1.id), None)
        self.assertIsNotNone(user1_member)
        user1_asset_ids = [a["id"] for a in user1_member["assets"]]
        self.assertIn(direct_asset.id, user1_asset_ids)

    def test_cabin_manager_with_direct_assigned_asset(self):
        """Cabin manager who has directly assigned assets must have them in cabin members."""
        manager_asset = Asset.objects.create(
            name="Manager MacBook Air",
            company="LP",
            category=self.cat_keyboard,
            assigned_to=self.user2,
            assigned_location=None,
        )

        serializer = LocationSerializer(self.cabin)
        data = serializer.data
        user2_member = next((m for m in data["members"] if m["id"] == self.user2.id), None)
        self.assertIsNotNone(user2_member)
        user2_asset_ids = [a["id"] for a in user2_member["assets"]]
        self.assertIn(manager_asset.id, user2_asset_ids)

    def test_asset_switch_from_employee_to_cabin_general(self):
        """Asset directly assigned to employee can be switched to cabin general asset."""
        asset = Asset.objects.create(
            name="Standing Desk",
            company="LP",
            category=self.cat_chair,
            assigned_to=self.user1,
            assigned_location=None,
        )
        # Switch to cabin general asset
        serializer = AssetSerializer(asset, data={"assigned_to": None, "assigned_location": self.cabin.id}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()

        self.assertIsNone(updated.assigned_to)
        self.assertEqual(updated.assigned_location.id, self.cabin.id)

        # Confirm in LocationSerializer general assets
        loc_data = LocationSerializer(self.cabin).data
        general_ids = [a["id"] for a in loc_data["general_assets"]]
        self.assertIn(updated.id, general_ids)

    def test_asset_category_auto_classification_on_save(self):
        """Creating an AssetCategory automatically sets canonical classification."""
        cat1 = AssetCategory.objects.create(name="Smartphones")
        self.assertEqual(cat1.classification, "Communication Systems")

        cat2 = AssetCategory.objects.create(name="Conference Chairs")
        self.assertEqual(cat2.classification, "Office Furniture")

        cat3 = AssetCategory.objects.create(name="Custom Sensor")
        self.assertEqual(cat3.classification, "General Assets")

    def test_uncategorized_asset_classification_inference(self):
        """Uncategorized assets infer classification from provider or hardware name."""
        sim_asset = Asset.objects.create(name="Office SIM", provider="Airtel", company="LP")
        self.assertEqual(sim_asset.classification, "Communication Systems")

        laptop_asset = Asset.objects.create(name="Dell Latitude Laptop", company="LP")
        self.assertEqual(laptop_asset.classification, "System Classification")

        chair_asset = Asset.objects.create(name="Ergonomic Desk Chair", company="LP")
        self.assertEqual(chair_asset.classification, "Office Furniture")

        unknown_asset = Asset.objects.create(name="Mysterious Gizmo", company="LP")
        self.assertEqual(unknown_asset.classification, "General Assets")

    def test_asset_auto_inherits_cabin_branch_on_save(self):
        """Asset assigned to cabin inherits the cabin branch if not explicitly set."""
        asset = Asset.objects.create(
            name="Cabin Projector",
            company="LP",
            category=self.cat_keyboard,
            assigned_location=self.cabin,
        )
        self.assertIsNotNone(asset.branch)
        self.assertEqual(asset.branch.id, self.branch.id)

    def test_cabin_members_deterministic_ordering_and_safe_blank_name(self):
        """LocationSerializer safely handles blank/whitespace cabin names and deterministic member ordering."""
        # Create second occupant with earlier alphabetical name
        User.objects.create_user(
            username="alice", first_name="Alice", email="alice@test.com", password="password123", company="LP", location=self.cabin.name
        )
        self.user1.first_name = "Bob"
        self.user1.location = f" {self.cabin.name} "
        self.user1.save()

        serializer = LocationSerializer(self.cabin)
        members = serializer.data["members"]
        # Manager is listed first
        self.assertTrue(members[0]["is_manager"])
        self.assertEqual(members[0]["id"], self.user2.id)

        # Non-managers are sorted alphabetically: Alice before Bob
        non_mgr_names = [m["first_name"] for m in members if not m["is_manager"]]
        self.assertEqual(non_mgr_names, ["Alice", "Bob"])


from rest_framework.test import APITestCase

class AssetAndSpaceAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="adminuser", email="admin@test.com", password="adminpassword", company="LP"
        )
        self.employee = User.objects.create_user(
            username="staff1", email="staff1@test.com", password="staffpassword", company="LP"
        )
        self.branch = Branch.objects.create(name="Calicut Branch", company="LP")
        self.cabin = Location.objects.create(name="Cabin 302", branch=self.branch, company="LP")
        self.category = AssetCategory.objects.create(name="Projector")
        self.client.force_authenticate(user=self.admin)

    def test_api_create_standalone_asset_with_employee(self):
        """API allows creating asset linked directly to an employee."""
        res = self.client.post("/api/assets/", {
            "name": "Employee Laptop",
            "category": self.category.id,
            "company": "LP",
            "assigned_to": self.employee.id,
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["assigned_to"], self.employee.id)
        self.assertIsNone(res.data["assigned_location"])

    def test_api_create_standalone_asset_with_cabin_as_general(self):
        """API allows creating asset linked directly to a cabin/space without employee."""
        res = self.client.post("/api/assets/", {
            "name": "Room Ceiling Fan",
            "category": self.category.id,
            "company": "LP",
            "assigned_location": self.cabin.id,
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["assigned_location"], self.cabin.id)
        self.assertIsNone(res.data["assigned_to"])

    def test_api_get_cabin_hierarchy_and_details(self):
        """API returns cabin details with members and general assets."""
        # Create general asset in cabin
        Asset.objects.create(
            name="Room AC",
            company="LP",
            assigned_location=self.cabin,
            category=self.category,
            assigned_to=None
        )
        # Create personal asset for employee in cabin
        Asset.objects.create(
            name="Staff Monitor",
            company="LP",
            assigned_location=self.cabin,
            category=self.category,
            assigned_to=self.employee
        )

        res = self.client.get(f"/api/locations/{self.cabin.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["general_assets"]), 1)
        self.assertEqual(res.data["general_assets"][0]["name"], "Room AC")
        self.assertEqual(len(res.data["members"]), 1)
        self.assertEqual(res.data["members"][0]["id"], self.employee.id)
        self.assertEqual(len(res.data["members"][0]["assets"]), 1)
        self.assertEqual(res.data["members"][0]["assets"][0]["name"], "Staff Monitor")

    def test_api_asset_location_details_is_minimal(self):
        """AssetSerializer uses LocationMinimalSerializer for assigned_location_details."""
        asset = Asset.objects.create(
            name="Test Router",
            company="LP",
            category=self.category,
            assigned_location=self.cabin,
        )
        res = self.client.get(f"/api/assets/{asset.id}/")
        self.assertEqual(res.status_code, 200)
        loc_details = res.data["assigned_location_details"]
        self.assertIsNotNone(loc_details)
        self.assertEqual(loc_details["id"], self.cabin.id)
        self.assertEqual(loc_details["name"], self.cabin.name)
        # Should not include heavy members field
        self.assertNotIn("members", loc_details)

    def test_staff_serializer_responsible_locations_uses_summary_and_has_role_names(self):
        """StaffSerializer includes role_names and uses summary serializer without heavy members."""
        self.employee.location = self.cabin.name
        self.employee.save()

        # Add asset to cabin
        Asset.objects.create(
            name="Cabin Printer",
            company="LP",
            category=self.category,
            assigned_location=self.cabin,
        )

        serializer = StaffSerializer(self.employee)
        data = serializer.data
        self.assertIn("role_names", data)
        self.assertIsInstance(data["role_names"], list)
        self.assertIn("responsible_locations", data)
        self.assertEqual(len(data["responsible_locations"]), 1)
        resp_loc = data["responsible_locations"][0]
        self.assertEqual(resp_loc["id"], self.cabin.id)
        self.assertIn("assigned_assets", resp_loc)
        self.assertEqual(len(resp_loc["assigned_assets"]), 1)
        # Should not include recursive heavy members
        self.assertNotIn("members", resp_loc)

    def test_location_summary_api_endpoint(self):
        """Location summary action returns category counts and general vs total assets."""
        Asset.objects.create(
            name="General Desk",
            company="LP",
            category=self.category,
            assigned_location=self.cabin,
            assigned_to=None
        )
        Asset.objects.create(
            name="Member Phone",
            company="LP",
            category=self.category,
            assigned_location=self.cabin,
            assigned_to=self.employee
        )

        res = self.client.get(f"/api/locations/summary/?company=LP")
        self.assertEqual(res.status_code, 200)
        cabin_sum = next((s for s in res.data if s["id"] == self.cabin.id), None)
        self.assertIsNotNone(cabin_sum)
        self.assertEqual(cabin_sum["total_assets"], 2)
        self.assertEqual(cabin_sum["general_assets_count"], 1)

    def test_api_delete_cabin(self):
        """API allows deleting a cabin space."""
        temp_cabin = Location.objects.create(name="Temporary Cabin", branch=self.branch, company="LP")
        res = self.client.delete(f"/api/locations/{temp_cabin.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Location.objects.filter(id=temp_cabin.id).exists())

    def test_uncategorized_and_generic_asset_classification_extended(self):
        """Assets named iPhone or MacBook, and generic-category assets with provider, classify correctly."""
        iphone = Asset.objects.create(name="iPhone 15 Pro", company="LP")
        self.assertEqual(iphone.classification, "Communication Systems")

        macbook = Asset.objects.create(name="MacBook Pro 16", company="LP")
        self.assertEqual(macbook.classification, "System Classification")

        ipad = Asset.objects.create(name="iPad Air M2", company="LP")
        self.assertEqual(ipad.classification, "Communication Systems")

        thinkpad = Asset.objects.create(name="ThinkPad X1 Carbon", company="LP")
        self.assertEqual(thinkpad.classification, "System Classification")

        # Category exists but resolves to General Assets; provider overrides to Communication Systems
        gen_cat = AssetCategory.objects.create(name="Miscellaneous Hardware", classification="General Assets")
        sim_with_gen_cat = Asset.objects.create(name="Company SIM", category=gen_cat, provider="Airtel", company="LP")
        self.assertEqual(sim_with_gen_cat.classification, "Communication Systems")

        # Category exists with General Assets, but asset name is a MacBook
        mac_with_gen_cat = Asset.objects.create(name="MacBook Air M1", category=gen_cat, company="LP")
        self.assertEqual(mac_with_gen_cat.classification, "System Classification")

    def test_staff_serializer_responsible_locations_includes_managed_spaces_without_location_string(self):
        """Space manager with empty user.location still gets their managed cabins in responsible_locations."""
        mgr = User.objects.create_user(
            username="manager_empty_loc", email="mgrempty@test.com", password="password123", company="LP", location=""
        )
        managed_cabin = Location.objects.create(
            name="Executive Suite", company="LP", branch=self.branch, assigned_to=mgr
        )
        serializer = StaffSerializer(mgr)
        resp_locs = serializer.data["responsible_locations"]
        self.assertEqual(len(resp_locs), 1)
        self.assertEqual(resp_locs[0]["id"], managed_cabin.id)
