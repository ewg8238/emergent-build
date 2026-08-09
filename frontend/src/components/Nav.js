import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { HardHat, LogOut } from "lucide-react";

export default function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Check if current user is admin by role or email
  const isAdmin = user?.role === "admin" || user?.email === process.env.REACT_APP_ADMIN_EMAIL;

  return (
    <nav className="glass sticky top-0 z-50 border-b border-neutral-200">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2" data-testid="nav-logo">
          <HardHat className="w-6 h-6" />
          <span className="font-head text-xl">COI Autopilot</span>
        </Link>
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <Link to="/dashboard" className="text-sm font-medium hover:opacity-60" data-testid="nav-dashboard">Dashboard</Link>
              {isAdmin && (
                <Link to="/prospects" className="text-sm font-medium hover:opacity-60" data-testid="nav-prospects">Prospects</Link>
              )}
              <Link to="/settings" className="text-sm font-medium hover:opacity-60" data-testid="nav-settings">Settings</Link>
              <button className="btn-outline !py-2 !px-4 flex items-center gap-2 text-sm"
                onClick={async () => { await logout(); navigate("/"); }} data-testid="nav-logout">
                <LogOut className="w-4 h-4" /> Logout
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="text-sm font-medium hover:opacity-60" data-testid="nav-login">Client Login</Link>
              <Link to="/register" className="btn-primary !py-2 !px-4 text-sm" data-testid="nav-signup">Automate Today</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
