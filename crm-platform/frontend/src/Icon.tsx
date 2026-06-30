import {
  Info,
  Eye, EyeOff, Smile, Paperclip, Phone, PhoneOff, MessageCircle, Send, Brain, Handshake, Forward, UserPlus,
  MoreHorizontal, CheckSquare, Check, Search, Package, TrendingUp, Megaphone, Wallet, CreditCard, ReceiptText,
  Truck, Calendar, Bell, Clock, Target, Gem, User, Users, Circle, Pencil, PenLine, Trash2, Link as LinkIcon,
  Pin, Gift, Zap, Plus, X, ChevronDown, Star, Flame, Trophy, GraduationCap, Lightbulb, AlertTriangle, FileText,
  Image as ImageIcon, Video, Settings, Home, LayoutGrid, List, ClipboardList, Filter, RefreshCw, Download, Upload,
  Mail, Lock, HelpCircle, ThumbsUp, Sparkles, PartyPopper, ShoppingBag, BadgeCheck, Banknote, Hash, Copy, Building2,
  Bot, MapPin, BarChart3, Palette, Tag, FolderOpen, Save, Camera, BookOpen, Briefcase, Rocket, Shield, ArrowLeftRight,
  Puzzle, Smartphone, Music, Menu, Plug, Landmark, Rss, Sun, Square, Award, MousePointerClick, PhoneIncoming, Coins,
  Instagram, Facebook,
  Coffee, Globe, Leaf, Mic, SlidersHorizontal, Factory, Folder, TrendingDown, Printer, Map as MapIcon, Ban, AppWindow, ListChecks, Calculator, Play, Pause,
} from "lucide-react";

const MAP: Record<string, any> = {
  eye: Eye, "eye-off": EyeOff, smile: Smile, paperclip: Paperclip, phone: Phone, chat: MessageCircle, send: Send,
  brain: Brain, handshake: Handshake, forward: Forward, "user-plus": UserPlus, more: MoreHorizontal,
  "check-square": CheckSquare, check: Check, message: MessageCircle, info: Info, search: Search, package: Package, "trending-up": TrendingUp, palette: Palette,
  megaphone: Megaphone, wallet: Wallet, card: CreditCard, receipt: ReceiptText, truck: Truck, calendar: Calendar,
  bell: Bell, clock: Clock, target: Target, gem: Gem, user: User, users: Users, circle: Circle, pencil: Pencil,
  trash: Trash2, link: LinkIcon, pin: Pin, gift: Gift, zap: Zap, plus: Plus, x: X, "chevron-down": ChevronDown,
  star: Star, flame: Flame, trophy: Trophy, coach: GraduationCap, bulb: Lightbulb, warn: AlertTriangle, file: FileText,
  image: ImageIcon, video: Video, settings: Settings, home: Home, grid: LayoutGrid, list: ClipboardList,
  filter: Filter, refresh: RefreshCw, download: Download, upload: Upload, mail: Mail, lock: Lock, thumb: ThumbsUp,
  sparkles: Sparkles, party: PartyPopper, bag: ShoppingBag, "badge-check": BadgeCheck, money: Banknote, hash: Hash,
  copy: Copy, building: Building2, bot: Bot, "map-pin": MapPin, chart: BarChart3,
  instagram: Instagram, facebook: Facebook, telegram: Send, tiktok: Music, viber: MessageCircle, whatsapp: MessageCircle, "📸": Instagram, calculator: Calculator, music: Music, play: Play, pause: Pause,
  "☕": Coffee, "🌐": Globe, "🌿": Leaf, "🎙": Mic, "🎙️": Mic, "🎛️": SlidersHorizontal, "🎛": SlidersHorizontal, "🏢": Building2, "🏭": Factory, "👆": MousePointerClick, "📁": Folder, "🔮": Sparkles, "🔻": TrendingDown, "🖨": Printer, "🖨️": Printer, "🖼": ImageIcon, "🖼️": ImageIcon, "🗺": MapIcon, "🗺️": MapIcon, "🚦": ListChecks, "🚫": Ban, "🪟": AppWindow,
  // --- emoji keys (mechanical sweep) ---
  "📞": Phone, "📋": ClipboardList, "🔍": Search, "🔗": LinkIcon, "💬": MessageCircle, "💰": Wallet, "💳": CreditCard,
  "📦": Package, "⚙": Settings, "⚙️": Settings, "🎯": Target, "🧾": ReceiptText, "👤": User, "👥": Users, "🚚": Truck,
  "✏": Pencil, "✏️": Pencil, "📝": FileText, "✉": Mail, "✉️": Mail, "🤝": Handshake, "🧠": Brain, "📌": Pin,
  "⚠": AlertTriangle, "⚠️": AlertTriangle, "🔒": Lock, "🏦": Landmark, "💾": Save, "🎁": Gift, "🎨": Palette,
  "📅": Calendar, "📣": Megaphone, "📊": BarChart3, "🗂": FolderOpen, "🗂️": FolderOpen, "📡": Rss, "☀": Sun, "☀️": Sun,
  "💯": Award, "💡": Lightbulb, "🏷": Tag, "🏷️": Tag, "🏠": Home, "⚡": Zap, "🕓": Clock, "🕐": Clock, "🕘": Clock,
  "📷": Camera, "✈": Send, "✈️": Send, "↪": Forward, "📎": Paperclip, "✍": PenLine, "✍️": PenLine, "🗑": Trash2,
  "🗑️": Trash2, "🤖": Bot, "💼": Briefcase, "🚀": Rocket, "📚": BookOpen, "📄": FileText, "💱": ArrowLeftRight,
  "🛡": Shield, "🛡️": Shield, "📤": Upload, "📵": PhoneOff, "📥": Download, "🧩": Puzzle, "✨": Sparkles, "🛍": ShoppingBag,
  "🛍️": ShoppingBag, "💎": Gem, "☑": CheckSquare, "☑️": CheckSquare, "📱": Smartphone, "🎵": Music, "☰": Menu,
  "🔄": RefreshCw, "🔌": Plug, "📈": TrendingUp, "😊": Smile, "👁": Eye, "👁️": Eye, "💵": Banknote, "💪": Award,
  "🔔": Bell, "➕": Plus, "🎉": PartyPopper, "🥳": PartyPopper, "🔝": TrendingUp, "📲": Smartphone, "💸": Coins,
  "🤩": Star, "🏆": Trophy, "🎓": GraduationCap, "📍": MapPin, "🟢": Circle, "🟡": Circle, "🔴": Circle, "🟦": Square,
  "🟣": Circle, "🟩": Square, "🟨": Square, "🟧": Square, "🟥": Square, "👍": ThumbsUp, "✅": Check, "🤔": HelpCircle,
};

export function Icon({ n, size = 16, strokeWidth = 2, style, ...rest }: { n: string; size?: number; strokeWidth?: number; style?: any; [k: string]: any }) {
  const C = MAP[n];
  if (!C) return <span style={{ fontSize: size, lineHeight: 1, ...(style || {}) }} aria-hidden="true">{n}</span>;
  return <C size={size} strokeWidth={strokeWidth} style={{ verticalAlign: "-3px", flexShrink: 0, ...(style || {}) }} {...rest} />;
}
