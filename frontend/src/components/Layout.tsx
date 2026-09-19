// react 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  ShieldCheck,
  LayoutDashboard,
  BarChart3,
  Terminal,
  Settings,
  Zap,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/console', icon: Terminal, label: 'Test Console' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-20 flex-shrink-0 flex flex-col border-r border-white/5 bg-surface-900 z-10">
        {/* Logo */}
        <div className="p-4 border-b border-white/5 flex justify-center">
          <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-black" />
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-6 space-y-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => isActive ? 'nav-item-active' : 'nav-item'}
              title={label}
            >
              <Icon className="w-5 h-5" />
            </NavLink>
          ))}
        </nav>

        {/* Status */}
        <div className="p-4 border-t border-white/5 flex justify-center">
          <div className="w-10 h-10 rounded-xl bg-surface-800 border border-white/10 flex items-center justify-center" title="Detection Active">
            <Zap className="w-5 h-5 text-brand-400 animate-pulse-slow" />
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
