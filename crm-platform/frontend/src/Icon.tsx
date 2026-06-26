import {
  Eye, EyeOff, Smile, Paperclip, Phone, MessageCircle, Send, Brain, Handshake, Forward, UserPlus,
  MoreHorizontal, CheckSquare, Check, Search, Package, TrendingUp, Megaphone, Wallet, CreditCard,
  ReceiptText, Truck, Calendar, Bell, Clock, Target, Gem, User, Circle, Pencil, Trash2, ArrowRight,
  CornerUpLeft, Link as LinkIcon, Pin, Gift, Zap, Plus, X, ChevronDown, Star, Flame, Trophy,
  GraduationCap, Lightbulb, AlertTriangle, FileText, Image as ImageIcon, Video, Settings, Users, Home,
  LayoutGrid, List, Filter, RefreshCw, Download, Upload, Mail, Lock, HelpCircle, ThumbsUp, Sparkles,
  PartyPopper, ShoppingBag, BadgeCheck, Banknote, Hash, Copy, Building2, Bot, MapPin, Phone as PhoneCall,
} from "lucide-react";

const MAP: Record<string, any> = {
  eye: Eye, "eye-off": EyeOff, smile: Smile, paperclip: Paperclip, phone: Phone, call: PhoneCall,
  chat: MessageCircle, send: Send, brain: Brain, handshake: Handshake, forward: Forward, "user-plus": UserPlus,
  more: MoreHorizontal, "check-square": CheckSquare, check: Check, search: Search, package: Package,
  "trending-up": TrendingUp, megaphone: Megaphone, wallet: Wallet, card: CreditCard, receipt: ReceiptText,
  truck: Truck, calendar: Calendar, bell: Bell, clock: Clock, target: Target, gem: Gem, user: User,
  circle: Circle, pencil: Pencil, trash: Trash2, "arrow-right": ArrowRight, "corner-up-left": CornerUpLeft,
  link: LinkIcon, pin: Pin, gift: Gift, zap: Zap, plus: Plus, x: X, "chevron-down": ChevronDown, star: Star,
  flame: Flame, trophy: Trophy, coach: GraduationCap, bulb: Lightbulb, warn: AlertTriangle, file: FileText,
  image: ImageIcon, video: Video, settings: Settings, users: Users, home: Home, grid: LayoutGrid, list: List,
  filter: Filter, refresh: RefreshCw, download: Download, upload: Upload, mail: Mail, lock: Lock,
  thumb: ThumbsUp, sparkles: Sparkles, party: PartyPopper, bag: ShoppingBag, "badge-check": BadgeCheck,
  money: Banknote, hash: Hash, copy: Copy, building: Building2, bot: Bot, "map-pin": MapPin,
};

export function Icon({ n, size = 16, strokeWidth = 2, style, ...rest }: { n: string; size?: number; strokeWidth?: number; style?: any; [k: string]: any }) {
  const C = MAP[n] || HelpCircle;
  return <C size={size} strokeWidth={strokeWidth} style={{ verticalAlign: "-3px", flexShrink: 0, ...(style || {}) }} {...rest} />;
}
